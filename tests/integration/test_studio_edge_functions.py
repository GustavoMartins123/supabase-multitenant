"""Function publication and credentials against disposable PostgreSQL databases."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))
sys.path.insert(0, str(ROOT / 'tests/smoke'))
DSN = os.environ.get('CONTROL_PLANE_TEST_DSN', '')


@unittest.skipUnless(DSN, 'Disposable CONTROL_PLANE_TEST_DSN required')
class StudioFunctionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        import httpx
        from fastapi import FastAPI, HTTPException
        from test_authorization_behavior import _seed_environment
        _seed_environment()
        os.environ.setdefault('META_ADMIN_DSN', 'postgres://platform_meta_admin:' + 'm' * 32 + '@database:5432/postgres')
        from app.schema_migrations import apply_migrations
        from app.routers import studio_edge_functions as routes
        self.routes = routes
        self.database = 'functions_test_' + secrets.token_hex(6)
        self.admin = await asyncpg.connect(DSN)
        await self.admin.execute(f'CREATE DATABASE "{self.database}"')
        self.pool = await asyncpg.create_pool(DSN.rsplit('/', 1)[0] + '/' + self.database, min_size=1, max_size=6)
        async with self.pool.acquire() as conn:
            await apply_migrations(conn)
        self.users = [uuid.uuid4() for _ in range(3)]
        self.projects = [uuid.uuid4() for _ in range(2)]
        self.refs = ['a' * 20, 'b' * 20]
        self.names = ['test_alpha', 'test_beta']
        await self.pool.executemany('INSERT INTO users(id,authelia_username) VALUES($1,$2)', [(u, 'tester' + str(i)) for i,u in enumerate(self.users)])
        await self.pool.executemany('INSERT INTO projects(id,name,display_name,public_ref,owner_id) VALUES($1,$2,$2,$3,$4)',
                                   [(p, self.names[i], self.refs[i], self.users[i]) for i,p in enumerate(self.projects)])
        await self.pool.executemany("INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,$3)",
                                   [(self.projects[0],self.users[0],'admin'),(self.projects[0],self.users[2],'member'),(self.projects[1],self.users[1],'admin')])
        self.temp = tempfile.TemporaryDirectory(prefix='functions-store-test-')
        self.root = Path(self.temp.name)
        for i, name in enumerate(self.names):
            directory = self.root / 'projects' / name
            directory.mkdir(parents=True)
            (directory / '.env').write_text(f'PROJECT_ID={name}\nPROJECT_UUID={self.projects[i]}\nPROJECT_PUBLIC_REF={self.refs[i]}\nJWT_SECRET_PROJETO=synthetic-{name}\nAPI_EXTERNAL_URL=https://api.example.com/{self.refs[i]}\n')
            projection = self.root / '.functions-tenants'
            projection.mkdir(exist_ok=True)
            (projection / (name + '.json')).write_text(json.dumps({'technical_name':name,'project_ref':self.refs[i],'project_uuid':str(self.projects[i]),'jwt_secret':'synthetic-' + name}))
        self.root_patch = patch.object(routes,'ROOT',self.root)
        self.root_patch.start()
        async def user(request,pool):
            identity = request.headers.get('X-Test-User')
            if not identity:
                raise HTTPException(401,'Authentication required')
            row = await pool.fetchrow('SELECT id,is_active FROM users WHERE id=$1',uuid.UUID(identity))
            if not row or not row['is_active']:
                raise HTTPException(403,'Inactive user')
            return {
                'db_user_id': row['id'],
                'is_global_admin': bool(await pool.fetchval("SELECT EXISTS(SELECT 1 FROM user_groups WHERE user_id=$1 AND group_name='admin')", row['id'])),
            }
        self.user_patch = patch.object(routes,'resolve_authenticated_user',side_effect=user)
        self.user_patch.start()
        app=FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.get_pool]=lambda:self.pool
        @app.middleware('http')
        async def service(request,call_next):
            request.state.internal_service=request.headers.get('X-Test-Service')
            return await call_next(request)
        @app.put('/api/projects/{ref}/settings')
        async def settings(ref:str,request: __import__('fastapi').Request):
            body=await request.json()
            from app.project_settings import _normalize_settings_updates
            updates=_normalize_settings_updates(body['settings'])
            await routes.configure_project(ref,updates,request,self.pool)
            return {'status':'updated'}
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.root_patch.stop();self.user_patch.stop()
        self.temp.cleanup()
        await self.pool.close()
        await self.admin.execute(f'DROP DATABASE "{self.database}" WITH (FORCE)')
        await self.admin.close()

    async def request(self,method,suffix='',body=None,project=0,user=0,service='studio-nginx'):
        return await self.client.request(method,f'/api/projects/{self.refs[project]}/edge-functions'+suffix,json=body,
            headers={'X-Test-User':str(self.users[user]),'X-Test-Service':service})

    async def configure(self,enabled,project=0,user=0,allowlist=None):
        settings={'EDGE_FUNCTIONS_ENABLED':str(enabled).lower()}
        if allowlist is not None:settings['FUNCTIONS_ALLOWED_NETWORK_HOSTS']=allowlist
        return await self.client.put(f'/api/projects/{self.refs[project]}/settings',json={'settings':settings},
                                    headers={'X-Test-User':str(self.users[user]),'X-Test-Service':'studio-nginx'})

    async def save(self,version='one',expected=None,project=0,user=0):
        result=await self.request('PUT','/my-function',{'expected_revision':expected,'files':[{'name':'index.ts','content':f'Deno.serve(()=>Response.json({{"version":"{version}"}}))'}]},project,user)
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    async def publish(self,draft,project=0,user=0):
        return await self.request('POST','/my-function/publish',{'revision':draft['revision'],'expected_published_revision':draft['published_revision']},project,user)

    async def remove(self, current, unpublish=False, project=0, user=0):
        return await self.request('POST' if unpublish else 'DELETE',
            '/my-function/unpublish' if unpublish else '/my-function',
            {'revision':current['revision'],'expected_published_revision':current['published_revision']},project,user)

    async def test_unpublish_and_delete_preserve_other_project_and_require_current_version(self):
        current=[]
        for i in (0,1):
            draft=await self.save(project=i,user=i)
            await self.configure(True,project=i,user=i)
            current.append((await self.publish(draft,project=i,user=i)).json())
        other=(self.root/'.functions-runtime/tenants/test_beta.json').read_bytes()
        response=await self.remove(current[0],unpublish=True)
        self.assertEqual(response.status_code,200,response.text)
        draft=response.json();self.assertIsNone(draft['published_revision'])
        self.assertEqual(draft['files'],current[0]['files'])
        self.assertEqual((self.root/'.functions-runtime/tenants/test_beta.json').read_bytes(),other)
        self.assertEqual((await self.publish(draft)).status_code,200)
        published=(await self.request('GET','/my-function')).json()
        newer=await self.save('two',expected=published['revision'])
        for action in (True,False):
            self.assertEqual((await self.remove(published,unpublish=action)).status_code,409)
        response=await self.remove(newer)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((await self.request('GET','/my-function')).status_code,404)
        self.assertEqual((await self.request('GET')).json()['functions'],[])
        self.assertEqual((self.root/'.functions-runtime/tenants/test_beta.json').read_bytes(),other)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM studio_edge_audit WHERE action IN ('unpublish','delete') AND outcome='completed'"),2)

    async def test_disabled_project_accepts_delete_and_unpublish_without_enabling_runtime(self):
        draft=await self.save();await self.configure(True)
        first=(await self.publish(draft)).json()
        await self.configure(False)
        response=await self.remove(first,unpublish=True)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((await self.remove(response.json())).status_code,200)
        self.assertFalse((self.root/'.functions-runtime/tenants/test_alpha.json').exists())
        self.assertIs(await self.pool.fetchval('SELECT enabled FROM project_edge_functions WHERE project_id=$1',self.projects[0]),False)

    async def test_interrupted_removal_recovers_only_the_activated_operation(self):
        import copy
        from app import edge_function_store as store, edge_functions

        other = await self.save(project=1, user=1)
        await self.configure(True, project=1, user=1)
        self.assertEqual((await self.publish(other, project=1, user=1)).status_code, 200)
        other_path = self.root / '.functions-runtime/tenants/test_beta.json'
        other_context = other_path.read_bytes()
        for action in ('unpublish', 'delete'):
            for activated in (False, True):
                with self.subTest(action=action, activated=activated):
                    current = await self.request('GET', '/my-function')
                    expected = current.json()['revision'] if current.status_code == 200 else None
                    draft = await self.save(f'{action}-{activated}', expected=expected)
                    self.assertEqual((await self.configure(True)).status_code, 200)
                    self.assertEqual((await self.publish(draft)).status_code, 200)
                    async with self.pool.acquire() as conn:
                        project = await self.routes.get_public_project_row(conn, self.refs[0])
                        previous = self.routes.load(project)
                        proposed = copy.deepcopy(previous)
                        if action == 'unpublish':
                            proposed['functions']['my-function']['published'] = None
                        else:
                            proposed['functions'].pop('my-function')
                        context = await self.routes.prepare(conn, project, proposed,
                            {'enabled': True, 'network_allowlist': []})
                        store.begin_publication(self.root, previous, proposed, context, action=action)
                        if activated:
                            edge_functions.activate_context(self.root, context)
                    response = await self.request('GET', '/my-function')
                    self.assertEqual(response.status_code, 404 if activated and action == 'delete' else 200)
                    recovered = store.read_state(self.root, self.names[0], str(self.projects[0]))
                    self.assertEqual(recovered, proposed if activated else previous)
                    runtime = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
                    files = store.published_files(self.root, self.names[0], str(self.projects[0]), state=recovered)
                    edge_functions.verify_generation(self.root, runtime, files)
                    self.assertFalse((self.root / '.functions-studio' / str(self.projects[0]) / 'publication.json').exists())
                    self.assertEqual(other_path.read_bytes(), other_context)

    async def test_failed_removal_preserves_state_and_reconfiguration_restores_publication(self):
        from app import edge_function_store as store

        state_path = self.root / '.functions-studio' / str(self.projects[0]) / 'state.json'
        original_atomic = store.atomic_json
        for action in ('unpublish', 'delete'):
            with self.subTest(action=action):
                current = await self.request('GET', '/my-function')
                expected = current.json()['revision'] if current.status_code == 200 else None
                draft = await self.save(action, expected=expected)
                await self.configure(True)
                published = (await self.publish(draft)).json()
                previous_state = state_path.read_bytes()
                context_path = self.root / '.functions-runtime/tenants/test_alpha.json'
                previous_context = context_path.read_bytes()
                failed = False

                def fail_state_once(path, value):
                    nonlocal failed
                    if path == state_path and not failed:
                        failed = True
                        raise OSError('synthetic interrupted state write')
                    return original_atomic(path, value)

                with patch.object(store, 'atomic_json', side_effect=fail_state_once):
                    result = await self.remove(published, unpublish=action == 'unpublish')
                self.assertEqual(result.status_code, 503, result.text)
                self.assertTrue(failed)
                self.assertEqual(state_path.read_bytes(), previous_state)
                self.assertFalse(context_path.exists())
                self.assertFalse(state_path.with_name('publication.json').exists())
                self.assertEqual((await self.request('GET', '/my-function')).json(), published)
                self.assertEqual((await self.configure(True)).status_code, 200)
                self.assertEqual(context_path.read_bytes(), previous_context)
                self.assertEqual(await self.pool.fetchval(
                    "SELECT count(*) FROM studio_edge_audit WHERE action=$1 AND outcome='failed'", action), 1)

    async def test_removing_while_disabled_cannot_republish_on_reenable(self):
        from app import edge_function_store as store

        for action in ('unpublish', 'delete'):
            with self.subTest(action=action):
                current = await self.request('GET', '/my-function')
                expected = current.json()['revision'] if current.status_code == 200 else None
                draft = await self.save(action, expected=expected)
                await self.configure(True)
                published = (await self.publish(draft)).json()
                self.assertEqual((await self.configure(False)).status_code, 200)
                result = await self.remove(published, unpublish=action == 'unpublish')
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual((await self.configure(True)).status_code, 200)
                self.assertEqual(store.published_files(self.root, self.names[0], str(self.projects[0])), {})
                current = await self.request('GET', '/my-function')
                if action == 'unpublish':
                    self.assertEqual(current.status_code, 200)
                    self.assertEqual(current.json()['revision'], published['revision'])
                    self.assertIsNone(current.json()['published_revision'])
                else:
                    self.assertEqual(current.status_code, 404)

    async def test_activation_drafts_publication_and_disable_are_independent(self):
        listing=await self.request('GET');body=listing.json();self.assertFalse(body['enabled']);self.assertEqual(body['functions'],[]);self.assertIn('limits',body)
        draft=await self.save()
        self.assertEqual((await self.publish(draft)).status_code,409)
        self.assertFalse((self.root/'.functions-runtime/tenants/test_alpha.json').exists())
        self.assertEqual((await self.configure(True)).status_code,200)
        self.assertEqual((await self.publish(draft)).status_code,200)
        context_path=self.root/'.functions-runtime/tenants/test_alpha.json'
        original=context_path.read_bytes()
        changed=await self.save('two',draft['revision'])
        self.assertEqual(context_path.read_bytes(),original)
        self.assertEqual((await self.publish(changed)).status_code,200)
        updated=context_path.read_bytes();self.assertNotEqual(updated,original)
        self.assertEqual((await self.configure(False)).status_code,200)
        self.assertFalse(context_path.exists())
        self.assertEqual((await self.publish(changed)).status_code,409)
        self.assertEqual((await self.configure(True)).status_code,200)
        self.assertEqual(context_path.read_bytes(),updated)

    async def test_same_function_name_never_shares_source_or_revisions_between_projects(self):
        first=await self.save()
        second=await self.save('two',project=1,user=1)
        self.assertNotEqual(first['revision'],second['revision'])
        for i,draft in enumerate((first,second)):
            self.assertEqual((await self.configure(True,i,i)).status_code,200)
            self.assertEqual((await self.publish(draft,i,i)).status_code,200)
        contexts=[json.loads((self.root/'.functions-runtime/tenants'/f'{name}.json').read_bytes()) for name in self.names]
        self.assertNotEqual(contexts[0]['env']['SUPABASE_SERVICE_ROLE_KEY'],contexts[1]['env']['SUPABASE_SERVICE_ROLE_KEY'])
        for i,context in enumerate(contexts):
            code=self.root/'.functions-runtime/code'/str(self.projects[i])/context['revision']/'my-function/index.ts'
            self.assertTrue(code.exists())
        self.assertEqual((await self.configure(False)).status_code,200)
        self.assertTrue((self.root/'.functions-runtime/tenants/test_beta.json').exists())

    async def test_member_other_project_and_unsigned_gateway_cannot_manage(self):
        for method,path,body in [('GET','',None),('PUT','/my-function',{'expected_revision':None,'files':[{'name':'index.ts','content':''}]}),('POST','/my-function/publish',{'revision':'a'*64,'expected_published_revision':None}),('POST','/my-function/unpublish',{'revision':'a'*64,'expected_published_revision':None}),('DELETE','/my-function',{'revision':'a'*64,'expected_published_revision':None})]:
            self.assertEqual((await self.request(method,path,body,user=2)).status_code,403)
            self.assertEqual((await self.request(method,path,body,user=1)).status_code,403)
            self.assertEqual((await self.request(method,path,body,service='forged')).status_code,403)
        self.assertEqual((await self.configure(True,user=2)).status_code,403)
        await self.pool.execute('UPDATE users SET is_active=false WHERE id=$1',self.users[0])
        self.assertEqual((await self.request('GET')).status_code,403)

    async def test_conflicting_drafts_publications_and_paths_are_rejected(self):
        draft=await self.save()
        self.assertEqual((await self.request('PUT','/my-function',{'expected_revision':None,'files':[{'name':'index.ts','content':''}]})).status_code,409)
        for name in ('../index.ts','/index.ts','.secret','sub/../../index.ts','sub//index.ts'):
            body={'expected_revision':draft['revision'],'files':[{'name':'index.ts','content':''},{'name':name,'content':'bad'}]}
            self.assertEqual((await self.request('PUT','/my-function',body)).status_code,400)
        self.assertEqual((await self.request('GET','/main')).status_code,400)
        self.assertEqual((await self.request('GET','?ref=' + self.refs[1])).status_code,400)
        self.assertEqual((await self.configure(True)).status_code,200)
        newer=await self.save('two',draft['revision'])
        self.assertEqual((await self.publish(draft)).status_code,409)
        self.assertEqual((await self.publish(newer)).status_code,200)

    async def test_internal_credentials_are_encrypted_scoped_and_never_returned(self):
        from app.opaque_keys import parse_opaque_key,OpaqueKeyError
        self.assertEqual((await self.configure(True)).status_code,200)
        context=json.loads((self.root/'.functions-runtime/tenants/test_alpha.json').read_bytes())
        keys=[context['env'][key] for key in ('SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY')]
        rows=await self.pool.fetch('SELECT kind,secret_ciphertext,secret_hash FROM project_function_keys WHERE project_id=$1',self.projects[0])
        self.assertEqual(len(rows),2)
        for token in keys:
            parsed=parse_opaque_key(self.projects[0],token)
            self.assertIn(parsed.kind,{'secret','publishable'})
            with self.assertRaises(OpaqueKeyError):parse_opaque_key(self.projects[1],token)
            self.assertNotIn(token,str(rows))
            self.assertNotIn(token,(await self.request('GET')).text)
        self.assertNotIn('platform_meta_admin',context['env']['SUPABASE_DB_URL'])
        self.assertIn('tenant_meta_'+self.projects[0].hex,context['env']['SUPABASE_DB_URL'])
        await self.configure(False);await self.configure(True)
        again=json.loads((self.root/'.functions-runtime/tenants/test_alpha.json').read_bytes())
        self.assertEqual(context['env'],again['env'])

    async def test_invalid_network_and_corrupt_storage_fail_closed(self):
        draft=await self.save();await self.configure(True);await self.publish(draft)
        for host in ('localhost:80','postgres-meta-global:8080','10.1.2.3:443','https://api.openai.com:443','*.example.com:443'):
            self.assertEqual((await self.configure(True,allowlist=host)).status_code,400)
        self.assertEqual((await self.configure(True,allowlist='api.openai.com:443')).status_code,200)
        context_path=self.root/'.functions-runtime/tenants/test_alpha.json'
        self.assertEqual(json.loads(context_path.read_bytes())['network_allowlist'],['api.openai.com:443'])
        self.assertEqual((await self.configure(True,allowlist='')).status_code,200)
        self.assertEqual(json.loads(context_path.read_bytes())['network_allowlist'],[])
        state=self.root/'.functions-studio'/str(self.projects[0])/'state.json'
        state.write_text('{broken')
        self.assertEqual((await self.request('GET')).status_code,503)
        self.assertFalse(context_path.exists())
        self.assertEqual((await self.configure(False)).status_code,200)

    async def test_interrupted_publication_recovers_only_the_saved_draft(self):
        from app import edge_function_store as store,edge_functions
        draft=await self.save();await self.configure(True)
        async with self.pool.acquire() as conn:
            project=await self.routes.get_public_project_row(conn,self.refs[0])
            state=self.routes.load(project)
            import copy
            proposed=copy.deepcopy(state);proposed['functions']['my-function']['published']=draft['revision']
            context=await self.routes.prepare(conn,project,proposed,{'enabled':True,'network_allowlist':[]})
            store.begin_publication(self.root,state,proposed,context)
            edge_functions.activate_context(self.root,context)
        recovered=await self.request('GET','/my-function')
        self.assertEqual(recovered.status_code,200,recovered.text)
        self.assertEqual(recovered.json()['published_revision'],draft['revision'])
        self.assertFalse((self.root/'.functions-studio'/str(self.projects[0])/'publication.json').exists())

    async def test_interrupted_publication_with_secrets_and_public_functions_keeps_runtime(self):
        from app import edge_function_store as store,edge_functions
        self.assertEqual((await self.request('PUT','/secrets',{'secrets':[{'name':'API_TOKEN','value':'value-1234'}]})).status_code,200)
        draft=await self.save()
        self.assertEqual((await self.request('PUT','/my-function/config',{'verify_jwt':False})).status_code,200)
        await self.configure(True)
        async with self.pool.acquire() as conn:
            project=await self.routes.get_public_project_row(conn,self.refs[0])
            state=self.routes.load(project)
            import copy
            proposed=copy.deepcopy(state);proposed['functions']['my-function']['published']=draft['revision']
            context=await self.routes.prepare(conn,project,proposed,{'enabled':True,'network_allowlist':[]})
            self.assertEqual(context['secrets'],{'API_TOKEN':'value-1234'})
            self.assertEqual(context['public_functions'],['my-function'])
            store.begin_publication(self.root,state,proposed,context)
            edge_functions.activate_context(self.root,context)
        recovered=await self.request('GET','/my-function')
        self.assertEqual(recovered.status_code,200,recovered.text)
        self.assertEqual(recovered.json()['published_revision'],draft['revision'])
        self.assertEqual(edge_functions.read_context(self.root,self.names[0],str(self.projects[0])),context)
        self.assertFalse((self.root/'.functions-studio'/str(self.projects[0])/'publication.json').exists())

    async def test_large_secret_context_still_starts_retention_of_replaced_generation(self):
        import time
        from app import edge_functions
        many=[{'name':f'S{index}','value':'v'*1015} for index in range(64)]
        self.assertEqual((await self.request('PUT','/secrets',{'secrets':many})).status_code,200)
        await self.configure(True)
        first=await self.save('one')
        self.assertEqual((await self.publish(first)).status_code,200)
        context=edge_functions.read_context(self.root,self.names[0],str(self.projects[0]))
        tenant=next((self.root/'.functions-runtime'/'tenants').glob(self.names[0]+'.json'))
        self.assertGreater(tenant.stat().st_size,65536)
        old=next(path for path in (self.root/'.functions-runtime'/'code').glob('*/'+context['revision']))
        os.utime(old,(time.time()-3600,time.time()-3600))
        second=await self.save('two',first['revision'])
        self.assertEqual((await self.publish(second)).status_code,200)
        self.assertTrue(old.is_dir())
        self.assertLess(time.time()-old.stat().st_mtime,60)

    async def test_undecryptable_secret_blocks_publish_with_conflict_and_can_be_replaced_or_deleted(self):
        from app import edge_functions
        self.assertEqual((await self.request('PUT','/secrets',{'secrets':[{'name':'STALE_A','value':'seed-a'},{'name':'STALE_B','value':'seed-b'}]})).status_code,200)
        async def corrupt(name):
            async with self.pool.acquire() as conn:
                foreign=await self.routes.encrypt_project_material(conn,project_id=self.projects[0],purpose='functions-env-secret:OTHER',plaintext='old-value')
                await conn.execute('UPDATE project_function_secrets SET secret_ciphertext=$3 WHERE project_id=$1 AND name=$2',self.projects[0],name,foreign)
        await self.configure(True)
        first=await self.save()
        self.assertEqual((await self.publish(first)).status_code,200)
        await corrupt('STALE_A');await corrupt('STALE_B')
        draft=await self.save('two',first['revision'])
        blocked=await self.publish(draft)
        self.assertEqual(blocked.status_code,409,blocked.text)
        self.assertIn('STALE_A',blocked.text)
        self.assertNotIn('old-value',blocked.text)
        self.assertEqual((await self.request('GET','/logs')).status_code,200)
        self.assertEqual((await self.request('DELETE','/secrets/STALE_A')).status_code,409)
        partial=await self.request('PUT','/secrets',{'secrets':[{'name':'STALE_A','value':'new-value-a'}]})
        self.assertEqual(partial.status_code,409,partial.text)
        self.assertIn('STALE_B',partial.text)
        fixed=await self.request('PUT','/secrets',{'secrets':[{'name':'STALE_A','value':'new-value-a'},{'name':'STALE_B','value':'new-value-b'}]})
        self.assertEqual(fixed.status_code,200,fixed.text)
        self.assertEqual((await self.request('DELETE','/secrets/STALE_B')).status_code,200)
        self.assertEqual((await self.publish(draft)).status_code,200)
        self.assertEqual(edge_functions.read_context(self.root,self.names[0],str(self.projects[0]))['secrets'],{'STALE_A':'new-value-a'})
        await corrupt('STALE_A')
        removed=await self.request('DELETE','/secrets/STALE_A')
        self.assertEqual(removed.status_code,200,removed.text)
        self.assertNotIn('secrets',edge_functions.read_context(self.root,self.names[0],str(self.projects[0])))

    async def test_log_reads_do_not_hold_the_configuration_lock_while_fetching(self):
        import fcntl
        draft=await self.save();await self.configure(True)
        self.assertEqual((await self.publish(draft)).status_code,200)
        lock_states=[]
        async def probe(conn,project,creds,secrets,*,function_name,level,limit):
            descriptor=os.open(self.root/'.functions-locks'/self.names[0],os.O_RDWR)
            try:
                fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
                lock_states.append(True)
            except BlockingIOError:
                lock_states.append(False)
            finally:
                os.close(descriptor)
            return {'logs':[],'runtime_connected':False}
        with patch.object(self.routes,'_fetch_merged_logs',side_effect=probe):
            self.assertEqual((await self.request('GET','/logs')).status_code,200)
            self.assertEqual((await self.request('GET','/my-function/logs')).status_code,200)
        self.assertEqual(lock_states,[True,True])

    async def test_raised_secret_quota_above_default_keeps_project_manageable(self):
        from app import edge_functions
        await self.configure(True)
        await self.pool.execute("UPDATE project_edge_functions SET quotas=$2::jsonb WHERE project_id=$1",
                                self.projects[0], json.dumps({'max_secrets': 100}))
        batch=[{'name':f'S{index}','value':f'value-{index:03d}'} for index in range(70)]
        self.assertEqual((await self.request('PUT','/secrets',{'secrets':batch})).status_code,200)
        draft=await self.save()
        published=await self.publish(draft)
        self.assertEqual(published.status_code,200,published.text)
        self.assertEqual(len(edge_functions.read_context(self.root,self.names[0],str(self.projects[0]))['secrets']),70)
        removed=await self.request('DELETE','/secrets/S1')
        self.assertEqual(removed.status_code,200,removed.text)
        self.assertEqual(len(edge_functions.read_context(self.root,self.names[0],str(self.projects[0]))['secrets']),69)

    async def test_schedule_scan_never_runs_publication_recovery_outside_the_lock(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock
        from app import edge_function_store as store
        await self.configure(True)
        draft=await self.save()
        self.assertEqual((await self.publish(draft)).status_code,200)
        created=await self.request('POST','/my-function/schedules',{'name':'tick','cron':'*/5 * * * *','enabled':True})
        self.assertEqual(created.status_code,200,created.text)
        due_at=datetime(2026,6,15,10,5,0,tzinfo=timezone.utc)
        await self.pool.execute('UPDATE project_edge_function_schedules SET next_run_at=$2 WHERE id=$1',
                                uuid.UUID(created.json()['schedule']['id']),due_at-timedelta(seconds=5))
        executed=AsyncMock(return_value=(200,{},'',False,1,'request-id',None))
        with patch.object(store,'recover_publication',side_effect=AssertionError('recovery without lock')) as recovery, \
             patch.object(self.routes,'_execute_function_http',executed):
            self.assertEqual(await self.routes.scan_edge_function_schedules(self.pool,now=due_at),1)
        recovery.assert_not_called()
        executed.assert_awaited_once()

    async def test_publishing_a_draft_outside_the_dependency_policy_returns_400_and_keeps_runtime(self):
        from app import edge_bundler, edge_functions
        await self.configure(True)
        first=await self.save()
        self.assertEqual((await self.publish(first)).status_code,200)
        active=edge_functions.read_context(self.root,self.names[0],str(self.projects[0]))
        with patch.object(edge_bundler,'validate_dependency_policy',return_value={}):
            legacy=await self.request('PUT','/my-function',{'expected_revision':first['revision'],'files':[{'name':'index.ts','content':'import x from "https://esm.sh/x"; Deno.serve(()=>new Response("v2"))'}]})
        self.assertEqual(legacy.status_code,200,legacy.text)
        draft=legacy.json()
        for path,body in (('/my-function/bundle',{'revision':draft['revision']}),
                          ('/my-function/publish',{'revision':draft['revision'],'expected_published_revision':draft['published_revision']})):
            refused=await self.request('POST',path,body)
            self.assertEqual(refused.status_code,400,(path,refused.text))
            self.assertIn('Disallowed import scheme',refused.text)
        self.assertEqual(edge_functions.read_context(self.root,self.names[0],str(self.projects[0])),active)

    async def test_management_works_with_a_single_database_connection(self):
        import asyncio,asyncpg
        original=self.pool
        limited=await asyncpg.create_pool(DSN.rsplit('/',1)[0]+'/'+self.database,min_size=1,max_size=1)
        self.pool=limited
        try:
            results=await asyncio.wait_for(asyncio.gather(self.request('GET'),self.request('GET')),timeout=5)
            self.assertTrue(all(result.status_code==200 for result in results))
        finally:
            self.pool=original
            await limited.close()

    async def test_failed_reconfiguration_persists_a_block_before_changing_runtime(self):
        draft=await self.save();await self.configure(True);await self.publish(draft)
        with patch.object(self.routes, 'prepare', side_effect=RuntimeError('synthetic publication failure')):
            result=await self.configure(True,allowlist='api.openai.com:443')
        self.assertEqual(result.status_code,503,result.text)
        self.assertIs(await self.pool.fetchval('SELECT enabled FROM project_edge_functions WHERE project_id=$1',self.projects[0]),False)
        self.assertFalse((self.root/'.functions-runtime/tenants/test_alpha.json').exists())
        self.assertEqual((await self.publish(draft)).status_code,409)
        self.assertEqual((await self.configure(True)).status_code,200)
        context=json.loads((self.root/'.functions-runtime/tenants/test_alpha.json').read_bytes())
        self.assertEqual(context['network_allowlist'],[])

    async def test_disable_recovers_interrupted_publication_before_withdrawing(self):
        from app import edge_function_store as store,edge_functions
        draft=await self.save();await self.configure(True)
        async with self.pool.acquire() as conn:
            project=await self.routes.get_public_project_row(conn,self.refs[0])
            state=self.routes.load(project)
            import copy
            proposed=copy.deepcopy(state);proposed['functions']['my-function']['published']=draft['revision']
            context=await self.routes.prepare(conn,project,proposed,{'enabled':True,'network_allowlist':[]})
            store.begin_publication(self.root,state,proposed,context)
            edge_functions.activate_context(self.root,context)
        self.assertEqual((await self.configure(False)).status_code,200)
        self.assertFalse((self.root/'.functions-runtime/tenants/test_alpha.json').exists())
        current=(await self.request('GET','/my-function')).json()
        self.assertEqual(current['published_revision'],draft['revision'])
        self.assertEqual((await self.configure(True)).status_code,200)
        current=(await self.request('GET','/my-function')).json()
        self.assertEqual(current['published_revision'],draft['revision'])

    async def test_reused_technical_name_cannot_inherit_the_deleted_projects_code(self):
        draft=await self.save();await self.configure(True);await self.publish(draft)
        await self.pool.execute('DELETE FROM projects WHERE id=$1',self.projects[0])
        replacement=uuid.uuid4()
        await self.pool.execute('INSERT INTO projects(id,name,display_name,public_ref,owner_id) VALUES($1,$2,$2,$3,$4)',replacement,self.names[0],self.refs[0],self.users[0])
        await self.pool.execute("INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'admin')",replacement,self.users[0])
        listing=await self.request('GET')
        body=listing.json();self.assertFalse(body['enabled']);self.assertEqual(body['functions'],[]);self.assertIn('limits',body)
        self.assertEqual((await self.publish(draft)).status_code,409)

    async def test_project_secrets_are_encrypted_scoped_injected_and_never_returned(self):
        from app import edge_functions, edge_function_store as store
        for bad_slug in ('secrets', 'logs', 'gc', 'config', 'health', 'versions'):
            with self.assertRaises(ValueError):
                store.function_name(bad_slug)
        for reserved in ('SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'JWT_SECRET', 'POSTGRES_PASSWORD', 'PATH', 'VERIFY_JWT', 'PROJECT_REF'):
            resp = await self.request('PUT', '/secrets', {'secrets': [{'name': reserved, 'value': 'blocked'}]})
            self.assertEqual(resp.status_code, 400, reserved)
        # Member and wrong-project admin cannot read or write secrets.
        self.assertEqual((await self.request('GET', '/secrets', user=2)).status_code, 403)
        self.assertEqual((await self.request('PUT', '/secrets', {'secrets': [{'name': 'STRIPE_KEY', 'value': 'sk_1'}]}, user=2)).status_code, 403)
        self.assertEqual((await self.request('GET', '/secrets', user=1, project=0)).status_code, 403)
        # Managing secrets before enabling or publishing persists encrypted ciphertext only.
        res = await self.request('PUT', '/secrets', {'secrets': [{'name': 'STRIPE_KEY', 'value': 'sk_alpha_1'}]})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()['runtime_synced'])
        self.assertNotIn('sk_alpha_1', res.text)
        listed = await self.request('GET', '/secrets')
        self.assertEqual([item['name'] for item in listed.json()['secrets']], ['STRIPE_KEY'])
        self.assertNotIn('sk_alpha_1', listed.text)
        raw_ct = await self.pool.fetchval('SELECT secret_ciphertext FROM project_function_secrets WHERE project_id=$1 AND name=$2', self.projects[0], 'STRIPE_KEY')
        self.assertTrue(raw_ct and 'sk_alpha_1' not in raw_ct)
        # Enabling and publishing includes project secrets in runtime context, isolated from beta.
        draft = await self.save()
        await self.configure(True)
        await self.publish(draft)
        ctx = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
        self.assertEqual(ctx['secrets'], {'STRIPE_KEY': 'sk_alpha_1'})
        self.assertEqual((await self.request('GET', '/secrets', user=1, project=1)).json()['secrets'], [])
        # Rotating while active immediately updates runtime revision and context.
        rot = await self.request('PUT', '/secrets', {'secrets': [{'name': 'STRIPE_KEY', 'value': 'sk_alpha_2'}]})
        self.assertEqual(rot.status_code, 200)
        self.assertTrue(rot.json()['runtime_synced'])
        ctx2 = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
        self.assertEqual(ctx2['secrets'], {'STRIPE_KEY': 'sk_alpha_2'})
        self.assertNotEqual(ctx2['revision'], ctx['revision'])
        # Deleting removes secret from DB and runtime context while keeping function alive.
        deleted = await self.request('DELETE', '/secrets/STRIPE_KEY')
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()['runtime_synced'])
        ctx3 = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
        self.assertNotIn('secrets', ctx3)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM studio_edge_audit WHERE action IN ('set_secret','delete_secret') AND outcome='completed'"), 3)

    async def test_per_function_verify_jwt_and_key_authorizer_admission(self):
        from app import edge_functions
        self.assertEqual((await self.request('PUT', '/my-function/config', {'verify_jwt': False})).status_code, 404)
        draft = await self.save()
        self.assertTrue(draft['verify_jwt'])
        self.assertEqual((await self.request('PUT', '/my-function/config', {'verify_jwt': False}, user=2)).status_code, 403)
        # Configuring before enablement/publish stores intent with published=false.
        cfg = await self.request('PUT', '/my-function/config', {'verify_jwt': False})
        self.assertEqual(cfg.status_code, 200, cfg.text)
        self.assertFalse(cfg.json()['verify_jwt'])
        row = await self.pool.fetchrow('SELECT verify_jwt, published FROM project_edge_function_configs WHERE project_id=$1 AND function_name=$2', self.projects[0], 'my-function')
        self.assertFalse(row['verify_jwt'])
        self.assertFalse(row['published'])
        # Enabling and publishing activates public_functions and marks published=true cleanly.
        await self.configure(True)
        pub_resp = await self.publish(draft)
        self.assertEqual(pub_resp.status_code, 200, pub_resp.text)
        pub = pub_resp.json()
        self.assertFalse(pub['verify_jwt'])
        ctx = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
        self.assertEqual(ctx['public_functions'], ['my-function'])
        row = await self.pool.fetchrow('SELECT verify_jwt, published FROM project_edge_function_configs WHERE project_id=$1 AND function_name=$2', self.projects[0], 'my-function')
        self.assertFalse(row['verify_jwt'])
        self.assertTrue(row['published'])
        # Unpublishing keeps verify_jwt=False preference while blocking published exposure.
        unpub_resp = await self.request('POST', '/my-function/unpublish', {'revision': pub['revision'], 'expected_published_revision': pub['published_revision']})
        self.assertEqual(unpub_resp.status_code, 200, unpub_resp.text)
        unpub = unpub_resp.json()
        self.assertFalse(unpub['verify_jwt'])
        row = await self.pool.fetchrow('SELECT verify_jwt, published FROM project_edge_function_configs WHERE project_id=$1 AND function_name=$2', self.projects[0], 'my-function')
        self.assertFalse(row['verify_jwt'])
        self.assertFalse(row['published'])
        # Re-publish and verify toggle back to True + delete cleanup.
        pub2_resp = await self.publish(unpub)
        self.assertEqual(pub2_resp.status_code, 200, pub2_resp.text)
        pub2 = pub2_resp.json()
        toggle_on = await self.request('PUT', '/my-function/config', {'verify_jwt': True})
        self.assertTrue(toggle_on.json()['verify_jwt'])
        self.assertNotIn('public_functions', edge_functions.read_context(self.root, self.names[0], str(self.projects[0])))
        self.assertEqual((await self.request('PUT', '/my-function/config', {'verify_jwt': False})).status_code, 200)
        # Verify real key-authorizer app allows anonymous calls ONLY for published verify_jwt=false slugs.
        import importlib.util, types
        from fastapi import HTTPException
        old_ka_env = {k: os.environ.get(k) for k in ('ACCESS_ADMISSION_SECRET',)}
        os.environ['ACCESS_ADMISSION_SECRET'] = 'a' * 64
        ka_dir = str(ROOT / 'servidor/key-authorizer')
        app_pkg_dir = str(ROOT / 'servidor/api-internal/app')
        sys.path.insert(0, app_pkg_dir)
        sys.path.insert(0, ka_dir)
        injected_mods = {}
        try:
            try:
                import redis.asyncio  # noqa: F401
            except ModuleNotFoundError:
                class _DummyRedisError(Exception): pass
                class _DummyRedis: pass
                for mod_name, attrs in (
                    ('redis', {}),
                    ('redis.asyncio', {'Redis': _DummyRedis}),
                    ('redis.exceptions', {'RedisError': _DummyRedisError}),
                ):
                    if mod_name not in sys.modules:
                        m = types.ModuleType(mod_name)
                        for k, v in attrs.items():
                            setattr(m, k, v)
                        injected_mods[mod_name] = m
                        sys.modules[mod_name] = m
            spec = importlib.util.spec_from_file_location('ka_app_test', ROOT / 'servidor/key-authorizer/app.py')
            ka_app = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ka_app)
            self.assertEqual(ka_app.extract_function_slug(f'/{self.refs[0]}/functions/v1/my-function/sub', self.refs[0]), 'my-function')
            self.assertIsNone(ka_app.extract_function_slug(f'/{self.refs[0]}/functions/v1/my-function%2fother', self.refs[0]))
            self.assertIsNone(ka_app.extract_function_slug(f'/{self.refs[0]}/functions/v1/main', self.refs[0]))
            async with self.pool.acquire() as ka_conn:
                proj_row = await ka_conn.fetchrow('SELECT id,public_ref,api_keyset_version FROM projects WHERE id=$1', self.projects[0])
                req_pub = ka_app.AdmissionRequest(project_ref=self.names[0], gateway_token='0'*64,
                    uri=f'/{self.refs[0]}/functions/v1/my-function', method='POST', client_ip='127.0.0.1',
                    api_key='', authorization='Stripe-Signature t=1')
                k, p, preserve = await ka_app.key_identity(ka_conn, proj_row, req_pub, 'functions', False, '')
                self.assertIsNone(k); self.assertIsNone(p); self.assertTrue(preserve)
                # Another slug defaults to protected -> fails 401 when missing apikey.
                req_priv = ka_app.AdmissionRequest(project_ref=self.names[0], gateway_token='0'*64,
                    uri=f'/{self.refs[0]}/functions/v1/other-fn', method='POST', client_ip='127.0.0.1',
                    api_key='', authorization='')
                with self.assertRaises(HTTPException) as ctx_err:
                    await ka_app.key_identity(ka_conn, proj_row, req_priv, 'functions', False, '')
                self.assertEqual(ctx_err.exception.status_code, 401)
                # Unpublish blocks anonymous admission immediately even with verify_jwt=false saved.
                await ka_conn.execute('UPDATE project_edge_function_configs SET published=false WHERE project_id=$1', self.projects[0])
                with self.assertRaises(HTTPException) as ctx_err2:
                    await ka_app.key_identity(ka_conn, proj_row, req_pub, 'functions', False, '')
                self.assertEqual(ctx_err2.exception.status_code, 401)
                await ka_conn.execute('UPDATE project_edge_function_configs SET published=true WHERE project_id=$1', self.projects[0])
                # Disabling service blocks even public webhooks with 404.
                await ka_conn.execute('UPDATE project_edge_functions SET enabled=false WHERE project_id=$1', self.projects[0])
                with self.assertRaises(HTTPException) as ctx_err3:
                    await ka_app.key_identity(ka_conn, proj_row, req_pub, 'functions', False, '')
                self.assertEqual(ctx_err3.exception.status_code, 404)
                await ka_conn.execute('UPDATE project_edge_functions SET enabled=true WHERE project_id=$1', self.projects[0])
        finally:
            for mod_name in injected_mods:
                sys.modules.pop(mod_name, None)
            for d in (ka_dir, app_pkg_dir):
                if d in sys.path:
                    sys.path.remove(d)
            for k, v in old_ka_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual((await self.request('DELETE', '/my-function', {'revision': pub2['revision'], 'expected_published_revision': pub2['published_revision']})).status_code, 200)
        self.assertIsNone(await self.pool.fetchrow('SELECT 1 FROM project_edge_function_configs WHERE project_id=$1 AND function_name=$2', self.projects[0], 'my-function'))

    async def test_logs_redaction_and_live_function_invoke(self):
        import base64
        import hashlib
        import hmac
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        name = self.names[0]
        ref = self.refs[0]
        tenant_id = str(self.projects[0])
        (self.root / 'projects' / name / '.env').write_text(
            f'PROJECT_ID={name}\nPROJECT_UUID={tenant_id}\nPROJECT_PUBLIC_REF={ref}\n'
            f'JWT_SECRET_PROJETO=synthetic-{name}\nANON_KEY_PROJETO=anon-jwt-{name}\n'
            f'SERVICE_ROLE_KEY_PROJETO=svc-jwt-{name}\nAPI_EXTERNAL_URL=https://api.example.com/{ref}\n'
        )
        (self.root / '.functions-tenants' / f'{name}.json').write_text(json.dumps({
            'technical_name': name,
            'project_ref': ref,
            'project_uuid': tenant_id,
            'jwt_secret': f'synthetic-{name}',
            'anon_key': f'anon-jwt-{name}',
            'service_role_key': f'svc-jwt-{name}',
        }))

        captured: list[dict] = []
        runtime_logs = [
            {
                'id': 'rt-1',
                'timestamp': '2099-01-01T00:00:05.000Z',
                'function_name': 'my-function',
                'level': 'info',
                'source': 'worker',
                'message': f'worker saw sk_mt_secret_999 and Bearer bearer-mt-secret and synthetic-{name}',
            },
            {
                'id': 'rt-2',
                'timestamp': '2099-01-01T00:00:06.000Z',
                'function_name': 'my-function',
                'level': 'error',
                'source': 'boot',
                'message': f'postgresql://u:dbpass_mt@db:5432/postgres anon-jwt-{name}',
            },
        ]

        class _StubRuntime(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_GET(self):
                if self.path.startswith('/__logs'):
                    ts = self.headers.get('X-Logs-Timestamp', '')
                    sig = self.headers.get('X-Logs-Signature', '')
                    expected = hmac.new(
                        f'synthetic-{name}'.encode('utf-8'),
                        f'edge-logs-v1\n{name}\n{tenant_id}\n{ref}\n{ts}'.encode('utf-8'),
                        hashlib.sha256,
                    ).hexdigest()
                    if not hmac.compare_digest(sig, expected):
                        self.send_response(403)
                        self.end_headers()
                        return
                    payload = json.dumps({'logs': runtime_logs}).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self._handle_invoke()

            def do_POST(self):
                self._handle_invoke()

            def _handle_invoke(self):
                length = int(self.headers.get('Content-Length', '0') or '0')
                raw = self.rfile.read(length) if length else b''
                captured.append({
                    'method': self.command,
                    'path': self.path,
                    'headers': {k.lower(): v for k, v in self.headers.items()},
                    'body': raw.decode('utf-8'),
                })
                resp = json.dumps({'ok': True, 'echo': raw.decode('utf-8')}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Request-ID', self.headers.get('X-Request-ID', 'none'))
                self.send_header('Set-Cookie', 'should-not-leak=1')
                self.send_header('Content-Length', str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

        server = ThreadingHTTPServer(('127.0.0.1', 0), _StubRuntime)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {'EDGE_FUNCTIONS_RUNTIME_URL': f'http://127.0.0.1:{server.server_address[1]}'}):
                self.assertEqual((await self.request('GET', '/logs', user=2)).status_code, 403)
                self.assertEqual((await self.request('GET', '/logs', user=1, project=0)).status_code, 403)
                self.assertEqual((await self.request('GET', '/logs?unknown=1')).status_code, 400)
                self.assertEqual((await self.request('GET', '/logs?limit=999')).status_code, 400)
                self.assertEqual((await self.request('GET', '/logs?level=trace')).status_code, 400)
                self.assertEqual((await self.request('POST', '/my-function/invoke', {'method': 'POST'}, user=2)).status_code, 403)

                await self.configure(True)
                draft = await self.save()
                self.assertEqual((await self.request('POST', '/my-function/invoke', {'method': 'POST'})).status_code, 409)
                self.assertEqual((await self.request('POST', '/my-function/invoke', {'method': 'TRACE'})).status_code, 400)
                self.assertEqual((await self.request('POST', '/my-function/invoke', {'path': '/../secret'})).status_code, 400)
                self.assertEqual((await self.request('POST', '/my-function/invoke', {'headers': {'X-Project-Ref': 'evil'}})).status_code, 400)
                self.assertEqual((await self.request('POST', '/my-function/invoke', {'headers': {'Authorization': 'Bearer x'}, 'auth_mode': 'anon'})).status_code, 400)

                self.assertEqual((await self.request('PUT', '/secrets', {'secrets': [{'name': 'WEBHOOK_SECRET', 'value': 'sk_mt_secret_999'}]})).status_code, 200)
                pub = (await self.publish(draft)).json()
                v2 = await self.save('two', draft['revision'])

                res_anon = await self.request('POST', '/my-function/invoke', {
                    'method': 'POST',
                    'path': '/items?ok=1',
                    'headers': {'X-Custom': 'mt'},
                    'body': '{"ping":2}',
                    'auth_mode': 'anon',
                })
                self.assertEqual(res_anon.status_code, 200, res_anon.text)
                body_anon = res_anon.json()
                self.assertTrue(body_anon['stale_draft_warning'])
                self.assertEqual(body_anon['executed_revision'], pub['published_revision'])
                self.assertEqual(body_anon['draft_revision'], v2['revision'])
                self.assertNotIn('set-cookie', body_anon['headers'])

                sent = captured[-1]
                self.assertEqual(sent['path'], '/my-function/items?ok=1')
                self.assertEqual(sent['headers']['x-project-name'], name)
                self.assertEqual(sent['headers']['x-project-ref'], ref)
                self.assertEqual(sent['headers']['apikey'], f'anon-jwt-{name}')
                claims = json.loads(base64.urlsafe_b64decode(sent['headers']['authorization'].split(' ')[1].split('.')[1] + '=='))
                self.assertEqual(claims['role'], 'anon')

                res_svc = await self.request('POST', '/my-function/invoke', {'method': 'GET', 'auth_mode': 'service_role'})
                self.assertEqual(res_svc.status_code, 200)
                svc_claims = json.loads(base64.urlsafe_b64decode(captured[-1]['headers']['authorization'].split(' ')[1].split('.')[1] + '=='))
                self.assertEqual(svc_claims['role'], 'service_role')
                self.assertEqual(captured[-1]['headers']['apikey'], f'svc-jwt-{name}')

                res_none = await self.request('POST', '/my-function/invoke', {'method': 'GET', 'auth_mode': 'none'})
                self.assertEqual(res_none.status_code, 200)
                self.assertNotIn('authorization', captured[-1]['headers'])
                self.assertNotIn('apikey', captured[-1]['headers'])

                res_custom = await self.request('POST', '/my-function/invoke', {
                    'method': 'GET',
                    'headers': {'Authorization': 'Bearer ext-mt-token'},
                    'auth_mode': 'custom',
                })
                self.assertEqual(res_custom.status_code, 200)
                self.assertEqual(captured[-1]['headers']['authorization'], 'Bearer ext-mt-token')

                logs_resp = await self.request('GET', '/logs?function=my-function&limit=20')
                self.assertEqual(logs_resp.status_code, 200, logs_resp.text)
                logs_data = logs_resp.json()
                self.assertTrue(logs_data['runtime_connected'])
                joined = json.dumps(logs_data['logs'])
                for secret_val in ('sk_mt_secret_999', 'bearer-mt-secret', f'synthetic-{name}', f'anon-jwt-{name}', 'dbpass_mt'):
                    self.assertNotIn(secret_val, joined)
                self.assertIn('[REDACTED]', joined)
                self.assertTrue(any(item['source'] == 'studio_test' for item in logs_data['logs']))
                self.assertTrue(any(item['source'] == 'worker' for item in logs_data['logs']))

                fn_logs = await self.request('GET', '/my-function/logs?level=error&limit=10')
                self.assertEqual(fn_logs.status_code, 200)
                self.assertTrue(all(item['level'] == 'error' for item in fn_logs.json()['logs']))
                self.assertGreaterEqual(await self.pool.fetchval("SELECT count(*) FROM studio_edge_audit WHERE action='test_invoke' AND outcome='completed'"), 4)
        finally:
            server.shutdown()
            server.server_close()

        with patch.dict(os.environ, {'EDGE_FUNCTIONS_RUNTIME_URL': 'http://127.0.0.1:9'}):
            down = await self.request('POST', '/my-function/invoke', {'method': 'GET'})
            self.assertEqual(down.status_code, 502)
            degraded_logs = await self.request('GET', '/my-function/logs')
            self.assertEqual(degraded_logs.status_code, 200)
            self.assertFalse(degraded_logs.json()['runtime_connected'])
            self.assertTrue(any(item['status'] == 502 for item in degraded_logs.json()['logs']))

    async def test_versions_rollback_bundle_download_limits_and_orphan_gc(self):
        import io
        import zipfile
        from app import edge_functions, edge_function_store as store

        self.assertEqual((await self.request('PUT', '/secrets', {'secrets': [{'name': 'EXPORT_BLOCKED', 'value': 'never-export-this-secret'}]})).status_code, 200)
        await self.configure(True)
        v1 = await self.save('version-1')
        self.assertIn('limits', v1)
        self.assertEqual(v1['limits']['memory_limit_mb'], 150)
        self.assertEqual(v1['limits']['max_concurrent_global'], 4)
        self.assertEqual(v1['limits']['max_concurrent_project'], 2)

        listed = (await self.request('GET', '')).json()
        self.assertEqual(listed['limits']['max_functions'], store.MAX_FUNCTIONS)

        self.assertEqual((await self.publish(v1)).status_code, 200)
        v2 = await self.save('version-2-orphan', v1['revision'])
        v3 = await self.save('version-3-draft', v2['revision'])

        self.assertEqual((await self.request('GET', '/my-function/versions', user=2)).status_code, 403)
        self.assertEqual((await self.request('GET', '/missing/versions')).status_code, 404)
        hist = (await self.request('GET', '/my-function/versions')).json()
        self.assertEqual(hist['draft_revision'], v3['revision'])
        self.assertEqual(hist['published_revision'], v1['revision'])
        revs = {item['revision']: item for item in hist['versions']}
        self.assertEqual(set(revs), {v1['revision'], v2['revision'], v3['revision']})
        self.assertTrue(revs[v1['revision']]['is_published'])
        self.assertTrue(revs[v3['revision']]['is_draft'])

        self.assertEqual((await self.request('GET', '/my-function/download', user=2)).status_code, 403)
        self.assertEqual((await self.request('GET', '/my-function/download?extra=1')).status_code, 400)
        self.assertEqual((await self.request('GET', '/my-function/download?version=invalid')).status_code, 400)
        dl_draft = await self.request('GET', '/my-function/download?version=draft')
        self.assertEqual(dl_draft.status_code, 200, dl_draft.text)
        self.assertEqual(dl_draft.headers['content-type'], 'application/zip')
        self.assertNotIn(b'never-export-this-secret', dl_draft.content)
        self.assertNotIn(b'synthetic-', dl_draft.content)
        with zipfile.ZipFile(io.BytesIO(dl_draft.content), 'r') as zf:
            self.assertEqual(set(zf.namelist()), {'my-function/index.ts', 'my-function/manifest.json'})
            self.assertIn('version-3-draft', zf.read('my-function/index.ts').decode('utf-8'))
            manifest = json.loads(zf.read('my-function/manifest.json'))
            self.assertEqual(manifest['revision'], v3['revision'])

        dl_pub = await self.request('GET', '/my-function/download?version=published')
        with zipfile.ZipFile(io.BytesIO(dl_pub.content), 'r') as zf:
            self.assertIn('version-1', zf.read('my-function/index.ts').decode('utf-8'))

        self.assertEqual((await self.request('POST', '/my-function/rollback', {'revision': v2['revision'], 'expected_revision': v2['revision']}, user=2)).status_code, 403)
        self.assertEqual((await self.request('POST', '/my-function/rollback', {'revision': v2['revision'], 'expected_revision': v1['revision']})).status_code, 409)
        self.assertEqual((await self.request('POST', '/my-function/rollback', {'revision': 'f' * 64, 'expected_revision': v3['revision']})).status_code, 404)
        runtime_before = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
        rb = await self.request('POST', '/my-function/rollback', {'revision': v2['revision'], 'expected_revision': v3['revision']})
        self.assertEqual(rb.status_code, 200, rb.text)
        rb_data = rb.json()
        self.assertEqual(rb_data['revision'], v2['revision'])
        self.assertEqual(rb_data['published_revision'], v1['revision'])
        self.assertEqual(edge_functions.read_context(self.root, self.names[0], str(self.projects[0])), runtime_before)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM studio_edge_audit WHERE action='rollback' AND outcome='completed'"), 1)

        self.assertEqual((await self.request('POST', '/gc', {}, user=2)).status_code, 403)
        kept_recent = (await self.request('POST', '/gc', {'min_age_seconds': 3600})).json()
        self.assertEqual(kept_recent['removed_count'], 0)
        cleaned = (await self.request('POST', '/gc', {'min_age_seconds': 0})).json()
        self.assertEqual(cleaned['removed_count'], 1)
        self.assertGreater(cleaned['reclaimed_bytes'], 0)
        hist_after = (await self.request('GET', '/my-function/versions')).json()
        self.assertEqual({item['revision'] for item in hist_after['versions']}, {v1['revision'], v2['revision']})

    async def test_backup_restore_and_delete_hygiene_never_auto_republishes_drafts(self):
        import subprocess, tarfile
        # Verify backup, restore, and delete scripts enforce functions archive safety and cleanup.
        backup_core = (ROOT / 'servidor/generateProject/lib/backup_core.sh').read_text(encoding='utf-8')
        restore_impl = (ROOT / 'servidor/generateProject/lib/restore_project_impl.sh').read_text(encoding='utf-8')
        delete_sh = (ROOT / 'servidor/generateProject/delete_project.sh').read_text(encoding='utf-8')
        self.assertIn('functions-studio.tar.gz', backup_core)
        self.assertIn('functions-studio.tar.gz', restore_impl)
        self.assertIn('ptrs["published"] = None', restore_impl)
        self.assertIn('.functions-studio/$project_uuid', delete_sh)
        self.assertIn('.functions-runtime/code/$project_uuid', delete_sh)

        # Simulate backup tar creation of .functions-studio and restore sanitization without auto-publishing.
        await self.configure(True)
        draft = await self.save('restored-draft')
        await self.publish(draft)
        studio_dir = self.root / '.functions-studio' / str(self.projects[0])
        self.assertTrue((studio_dir / 'state.json').is_file())
        with tempfile.TemporaryDirectory(prefix='fn-restore-test-') as tmp:
            tmp_root = Path(tmp)
            archive = tmp_root / 'functions-studio.tar.gz'
            with tarfile.open(archive, 'w:gz') as tf:
                for p in studio_dir.rglob('*'):
                    tf.add(p, arcname=p.relative_to(studio_dir).as_posix(), recursive=False)
            stage = tmp_root / 'restored'
            stage.mkdir()
            with tarfile.open(archive, 'r:gz') as tf:
                for member in tf.getmembers():
                    self.assertFalse(member.issym() or member.islnk())
                tf.extractall(stage, filter='data')
            (stage / 'publication.json').write_text('{"stale":true}')
            (stage / 'publication.json').unlink()
            state = json.loads((stage / 'state.json').read_text(encoding='utf-8'))
            for ptrs in state['functions'].values():
                ptrs['published'] = None
            (stage / 'state.json').write_text(json.dumps(state))
            sanitized = json.loads((stage / 'state.json').read_text(encoding='utf-8'))
            self.assertEqual(sanitized['functions']['my-function']['draft'], draft['revision'])
            self.assertIsNone(sanitized['functions']['my-function']['published'])

        # Symlink in archive must be rejected when validating restore archive.
        with tempfile.TemporaryDirectory(prefix='fn-sym-test-') as tmp:
            bad_tar = Path(tmp) / 'bad.tar.gz'
            with tarfile.open(bad_tar, 'w:gz') as tf:
                info = tarfile.TarInfo('state.json')
                info.type = tarfile.SYMTYPE
                info.linkname = '/etc/passwd'
                tf.addfile(info)
            with tarfile.open(bad_tar, 'r:gz') as tf:
                self.assertTrue(any(m.issym() for m in tf.getmembers()))

        proc = subprocess.run(
            ['bash', '-n', str(ROOT / 'servidor/generateProject/lib/backup_core.sh'),
             str(ROOT / 'servidor/generateProject/lib/restore_project_impl.sh'),
             str(ROOT / 'servidor/generateProject/delete_project.sh')],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    async def test_templates_author_attribution_version_detail_and_line_diff(self):
        from app import edge_function_store as store
        await self.pool.execute(
            "INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'admin')",
            self.projects[1], self.users[0],
        )
        await self.pool.execute(
            "INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'admin') ON CONFLICT DO NOTHING",
            self.projects[0], self.users[1],
        )

        # Templates catalog returns curated valid bundles and reserved names cannot be deployed as functions.
        tpl_resp = await self.request('GET', '/templates')
        self.assertEqual(tpl_resp.status_code, 200, tpl_resp.text)
        templates = tpl_resp.json()['templates']
        tpl_ids = {t['id'] for t in templates}
        self.assertTrue({'hello-world', 'webhook-hmac', 'project-rest', 'streaming-sse', 'websocket-echo', 'scheduled-cron'}.issubset(tpl_ids))
        for tpl in templates:
            self.assertEqual(store.validate_files(tpl['files']), sorted(tpl['files'], key=lambda f: f['name']))
        for reserved in ('templates', 'quotas', 'alerts', 'schedules', 'registries'):
            with self.assertRaises(ValueError):
                store.function_name(reserved)
            bad = await self.request('PUT', f'/{reserved}', {'expected_revision': None, 'files': [{'name': 'index.ts', 'content': 'x'}]})
            self.assertIn(bad.status_code, (400, 405, 422))

        # Multi-author drafts record creator attribution per revision.
        v1 = (await self.request('PUT', '/hello', {
            'expected_revision': None,
            'files': [{'name': 'index.ts', 'content': 'console.log("v1");\nreturn 1;\n'}],
        }, user=0)).json()
        v2 = (await self.request('PUT', '/hello', {
            'expected_revision': v1['revision'],
            'files': [
                {'name': 'index.ts', 'content': 'console.log("v2");\nreturn 2;\n'},
                {'name': 'helper.ts', 'content': 'export const ok = true;\n'},
            ],
        }, user=1)).json()

        versions = (await self.request('GET', '/hello/versions')).json()['versions']
        by_rev = {item['revision']: item for item in versions}
        self.assertEqual(by_rev[v1['revision']]['author_id'], str(self.users[0]))
        self.assertEqual(by_rev[v1['revision']]['author_label'], 'tester0')
        self.assertEqual(by_rev[v2['revision']]['author_id'], str(self.users[1]))
        self.assertEqual(by_rev[v2['revision']]['author_label'], 'tester1')

        # Single version snapshot endpoint validates revision and returns immutable files + author.
        snap_resp = await self.request('GET', f"/hello/versions/{v1['revision']}")
        self.assertEqual(snap_resp.status_code, 200, snap_resp.text)
        snap = snap_resp.json()
        self.assertEqual(snap['author_label'], 'tester0')
        self.assertEqual(snap['files'][0]['content'], 'console.log("v1");\nreturn 1;\n')
        self.assertEqual((await self.request('GET', '/hello/versions/not-a-sha')).status_code, 400)
        self.assertEqual((await self.request('GET', f"/hello/versions/{'0'*64}")).status_code, 404)

        # Line-by-line unified diff between revisions and selectors.
        diff_resp = await self.request('GET', f"/hello/diff?from={v1['revision']}&to=draft")
        self.assertEqual(diff_resp.status_code, 200, diff_resp.text)
        diff = diff_resp.json()
        self.assertEqual(diff['from_revision'], v1['revision'])
        self.assertEqual(diff['to_revision'], v2['revision'])
        self.assertEqual(diff['summary']['files_added'], 1)
        self.assertEqual(diff['summary']['files_modified'], 1)
        by_file = {f['name']: f for f in diff['files']}
        self.assertEqual(by_file['helper.ts']['status'], 'added')
        self.assertEqual(by_file['index.ts']['status'], 'modified')
        self.assertIn('-console.log("v1");', by_file['index.ts']['hunks'])
        self.assertIn('+console.log("v2");', by_file['index.ts']['hunks'])
        self.assertEqual((await self.request('GET', '/hello/diff')).status_code, 400)
        self.assertEqual((await self.request('GET', '/hello/diff?from=published&to=draft')).status_code, 409)

        # Deleting the function clears revision authorship rows.
        del_resp = await self.request('DELETE', '/hello', {'revision': v2['revision'], 'expected_published_revision': None})
        self.assertEqual(del_resp.status_code, 200, del_resp.text)
        self.assertEqual(
            await self.pool.fetchval("SELECT count(*) FROM project_edge_function_revisions WHERE project_id=$1 AND function_name='hello'", self.projects[0]),
            0,
        )

    async def test_custom_project_quotas_runtime_limits_and_saturation_alerts(self):
        from app import edge_functions
        await self.configure(True)
        # Project admin cannot raise limits above platform defaults, but can tighten limits & alert thresholds.
        denied_raise = await self.request('PUT', '/quotas', {'memory_limit_mb': 256, 'max_concurrent_project': 4})
        self.assertEqual(denied_raise.status_code, 403, denied_raise.text)
        tightened = await self.request('PUT', '/quotas', {'max_functions': 2, 'max_bytes': 10000, 'max_secrets': 1, 'alert_threshold_pct': 50})
        self.assertEqual(tightened.status_code, 200, tightened.text)
        self.assertEqual(tightened.json()['quotas']['max_functions'], 2)
        self.assertEqual(tightened.json()['quotas']['alert_threshold_pct'], 50)

        # Enforces tightened per-project function count, bundle byte size, and secret caps.
        d1 = (await self.request('PUT', '/fn-one', {'expected_revision': None, 'files': [{'name': 'index.ts', 'content': 'export {};'}]})).json()
        self.assertEqual((await self.request('POST', '/fn-one/publish', {'revision': d1['revision'], 'expected_published_revision': None})).status_code, 200)
        too_big = await self.request('PUT', '/fn-two', {'expected_revision': None, 'files': [{'name': 'index.ts', 'content': 'x' * 11000}]})
        self.assertEqual(too_big.status_code, 400)
        self.assertEqual((await self.request('PUT', '/fn-two', {'expected_revision': None, 'files': [{'name': 'index.ts', 'content': 'Deno.serve(()=>new Response("ok"))'}]})).status_code, 200)
        third_fn = await self.request('PUT', '/fn-three', {'expected_revision': None, 'files': [{'name': 'index.ts', 'content': 'x'}]})
        self.assertEqual(third_fn.status_code, 409)
        self.assertEqual((await self.request('PUT', '/secrets', {'secrets': [{'name': 'S1', 'value': 'v1'}]})).status_code, 200)
        sec_cap = await self.request('PUT', '/secrets', {'secrets': [{'name': 'S2', 'value': 'v2'}]})
        self.assertEqual(sec_cap.status_code, 400)

        # Near-limit alert fires at >= 50% (we hit 2/2 = 100% functions & 1/1 = 100% secrets).
        alerts_resp = await self.request('GET', '/alerts')
        self.assertEqual(alerts_resp.status_code, 200, alerts_resp.text)
        active = alerts_resp.json()['active_alerts']
        self.assertTrue(any(a['metric'] == 'functions_count' and a['severity'] == 'critical' for a in active), active)
        self.assertTrue(any(a['metric'] == 'secrets_count' and a['severity'] == 'critical' for a in active), active)
        events = alerts_resp.json()['events']
        self.assertTrue(any(e['kind'] == 'quota_updated' and not e['acknowledged'] for e in events))
        ack_id = events[0]['id']
        ack_resp = await self.request('POST', f'/alerts/{ack_id}/ack')
        self.assertEqual(ack_resp.status_code, 200, ack_resp.text)
        self.assertTrue(ack_resp.json()['acknowledged'])
        self.assertEqual([e['id'] for e in (await self.request('GET', '/alerts')).json()['events'] if e['id'] == ack_id], [])

        # Global platform admin can raise limits within ceilings and propagate them to runtime context JSON.
        await self.pool.execute("INSERT INTO user_groups(user_id,group_name,source) VALUES($1,'admin','test')", self.users[0])
        raised = await self.request('PUT', '/quotas', {'memory_limit_mb': 256, 'worker_timeout_ms': 90000, 'max_concurrent_project': 4, 'max_functions': 200, 'max_bytes': 2000000})
        self.assertEqual(raised.status_code, 200, raised.text)
        ctx = edge_functions.read_context(self.root, 'test_alpha', str(self.projects[0]))
        self.assertEqual(ctx['limits'], {'memory_limit_mb': 256, 'worker_timeout_ms': 90000, 'max_concurrent_project': 4})

        # Out-of-bounds ceiling values are rejected.
        self.assertEqual((await self.request('PUT', '/quotas', {'max_concurrent_project': 9})).status_code, 400)
        reset = await self.request('PUT', '/quotas', {'reset_defaults': True})
        self.assertEqual(reset.status_code, 200, reset.text)
        ctx_after = edge_functions.read_context(self.root, 'test_alpha', str(self.projects[0]))
        self.assertNotIn('limits', ctx_after)

    async def test_wasm_binary_artifacts_validation_publish_diff_and_zip(self):
        import base64, io, zipfile
        await self.configure(True)
        wasm_bytes = bytes([
            0x00, 0x61, 0x73, 0x6D, 0x01, 0x00, 0x00, 0x00,
            0x01, 0x07, 0x01, 0x60, 0x02, 0x7F, 0x7F, 0x01, 0x7F,
            0x03, 0x02, 0x01, 0x00,
            0x07, 0x07, 0x01, 0x03, 0x61, 0x64, 0x64, 0x00, 0x00,
            0x0A, 0x09, 0x01, 0x07, 0x00, 0x20, 0x00, 0x20, 0x01, 0x6A, 0x0B,
        ])
        wasm_b64 = base64.b64encode(wasm_bytes).decode('ascii')

        # Non-.wasm filenames and non-WASM binaries are rejected cleanly.
        bad_ext = await self.request('PUT', '/wasm-fn', {
            'expected_revision': None,
            'files': [
                {'name': 'index.ts', 'content': 'export {};'},
                {'name': 'evil.bin', 'content': wasm_b64, 'encoding': 'base64'},
            ],
        })
        self.assertEqual(bad_ext.status_code, 400)
        bad_magic = await self.request('PUT', '/wasm-fn', {
            'expected_revision': None,
            'files': [
                {'name': 'index.ts', 'content': 'export {};'},
                {'name': 'fake.wasm', 'content': base64.b64encode(b'NOT_WASM_HEADER').decode('ascii'), 'encoding': 'base64'},
            ],
        })
        self.assertEqual(bad_magic.status_code, 400)

        v1 = await self.request('PUT', '/wasm-fn', {
            'expected_revision': None,
            'files': [
                {'name': 'index.ts', 'content': 'import * as mod from "./add.wasm";\nDeno.serve(()=>Response.json({s:mod.add(1,2)}));\n'},
                {'name': 'add.wasm', 'content': wasm_b64, 'encoding': 'base64'},
            ],
        })
        self.assertEqual(v1.status_code, 200, v1.text)
        rev1 = v1.json()['revision']
        pub = await self.request('POST', '/wasm-fn/publish', {'revision': rev1, 'expected_published_revision': None})
        self.assertEqual(pub.status_code, 200, pub.text)

        from app import edge_functions
        ctx = edge_functions.read_context(self.root, 'test_alpha', str(self.projects[0]))
        mat_path = self.root / '.functions-runtime/code' / str(self.projects[0]) / ctx['revision'] / 'wasm-fn/add.wasm'
        self.assertEqual(mat_path.read_bytes(), wasm_bytes)

        zip_resp = await self.request('GET', '/wasm-fn/download?version=published')
        self.assertEqual(zip_resp.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(zip_resp.content), 'r') as zf:
            self.assertEqual(zf.read('wasm-fn/add.wasm'), wasm_bytes)

        v2 = (await self.request('PUT', '/wasm-fn', {
            'expected_revision': rev1,
            'files': [
                {'name': 'index.ts', 'content': 'import * as mod from "./add.wasm";\nDeno.serve(()=>Response.json({s:mod.add(1,2)}));\n'},
                {'name': 'add.wasm', 'content': base64.b64encode(wasm_bytes + b'\x00\x02').decode('ascii'), 'encoding': 'base64'},
            ],
        })).json()
        diff = (await self.request('GET', f"/wasm-fn/diff?from={rev1}&to={v2['revision']}")).json()
        wasm_diff = next(f for f in diff['files'] if f['name'] == 'add.wasm')
        self.assertTrue(wasm_diff['binary'])
        self.assertEqual(wasm_diff['status'], 'modified')
        self.assertIn('binary wasm file', wasm_diff['hunks'][0])

    async def test_cron_schedules_execution_advisory_lock_and_auto_cleanup(self):
        from datetime import datetime, timedelta, timezone
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from app import edge_function_store as store

        # 1. Cron parser & Vixie calendar semantics.
        self.assertEqual(store.validate_cron_expression('@hourly'), '0 * * * *')
        self.assertEqual(store.validate_cron_expression('*/15 9-17 * jan-dec mon-fri'), '*/15 9-17 * jan-dec mon-fri')
        leap_next = store.next_cron_run('0 12 29 2 *', datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(leap_next, datetime(2028, 2, 29, 12, 0, tzinfo=timezone.utc))
        vixie_or = store.next_cron_run('0 0 15 * mon', datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(vixie_or, datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc))
        for bad_expr in ('* * * *', '60 * * * *', '*/0 * * * *', '5-2 * * * *', '0 0 30 2 *', '0 0 * 13 *'):
            with self.assertRaises(ValueError):
                store.validate_cron_expression(bad_expr)

        # 2. Setup runtime stub & project credentials.
        name, ref, tenant_id = self.names[0], self.refs[0], str(self.projects[0])
        (self.root / 'projects' / name / '.env').write_text(
            f'PROJECT_ID={name}\nPROJECT_UUID={tenant_id}\nPROJECT_PUBLIC_REF={ref}\n'
            f'JWT_SECRET_PROJETO=synthetic-{name}\nANON_KEY_PROJETO=anon-jwt-{name}\n'
            f'SERVICE_ROLE_KEY_PROJETO=svc-jwt-{name}\nAPI_EXTERNAL_URL=https://api.example.com/{ref}\n'
        )
        (self.root / '.functions-tenants' / f'{name}.json').write_text(json.dumps({
            'technical_name': name,
            'project_ref': ref,
            'project_uuid': tenant_id,
            'jwt_secret': f'synthetic-{name}',
            'anon_key': f'anon-jwt-{name}',
            'service_role_key': f'svc-jwt-{name}',
        }))
        captured: list[dict] = []

        class _CronStub(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0') or '0')
                raw = self.rfile.read(length) if length else b''
                captured.append({'path': self.path, 'body': raw.decode('utf-8'), 'headers': {k.lower(): v for k, v in self.headers.items()}})
                resp = b'{"scheduled":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

        server = ThreadingHTTPServer(('127.0.0.1', 0), _CronStub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {'EDGE_FUNCTIONS_RUNTIME_URL': f'http://127.0.0.1:{server.server_address[1]}'}):
                draft = await self.save()
                # Disabled project / unpublished function guards.
                self.assertEqual((await self.request('POST', '/my-function/schedules', {'name': 's1', 'cron': '*/5 * * * *', 'enabled': True})).status_code, 409)
                await self.configure(True)
                self.assertEqual((await self.request('POST', '/my-function/schedules', {'name': 's1', 'cron': '*/5 * * * *', 'enabled': True})).status_code, 409)
                paused = await self.request('POST', '/my-function/schedules', {'name': 'paused', 'cron': '@daily', 'enabled': False})
                self.assertEqual(paused.status_code, 200, paused.text)
                self.assertFalse(paused.json()['schedule']['enabled'])

                await self.publish(draft)
                # Access & validation boundaries.
                self.assertEqual((await self.request('GET', '/schedules', user=2)).status_code, 403)
                self.assertEqual((await self.request('POST', '/my-function/schedules', {'name': 'bad', 'cron': '99 * * * *'})).status_code, 400)
                self.assertEqual((await self.request('POST', '/my-function/schedules', {'name': 'bad-hdr', 'cron': '*/5 * * * *', 'headers': {'X-Project-Ref': 'evil'}})).status_code, 400)

                created = await self.request('POST', '/my-function/schedules', {
                    'name': 'tick-every-5m',
                    'cron': '*/5 * * * *',
                    'method': 'POST',
                    'path': '/cron?source=scheduler',
                    'headers': {'X-Job': 'nightly'},
                    'body': '{"task":"cleanup"}',
                    'auth_mode': 'service_role',
                    'enabled': True,
                })
                self.assertEqual(created.status_code, 200, created.text)
                sched = created.json()['schedule']
                sched_id = sched['id']
                self.assertTrue(sched['enabled'])
                self.assertIsNotNone(sched['next_run_at'])
                # Duplicate name rejected cleanly.
                self.assertEqual((await self.request('POST', '/my-function/schedules', {'name': 'tick-every-5m', 'cron': '*/5 * * * *'})).status_code, 409)

                # Project-wide and per-function listing both see the schedules.
                proj_scheds = (await self.request('GET', '/schedules')).json()['schedules']
                fn_scheds = (await self.request('GET', '/my-function/schedules')).json()['schedules']
                self.assertEqual(len(proj_scheds), 2)
                self.assertEqual(len(fn_scheds), 2)

                # Manual trigger executes immediately & records cron invocation log.
                trig = await self.request('POST', f'/my-function/schedules/{sched_id}/trigger')
                self.assertEqual(trig.status_code, 200, trig.text)
                self.assertEqual(trig.json()['invocation']['status'], 200)
                self.assertEqual(captured[-1]['path'], '/my-function/cron?source=scheduler')
                self.assertEqual(captured[-1]['body'], '{"task":"cleanup"}')
                self.assertEqual(captured[-1]['headers']['x-job'], 'nightly')
                self.assertEqual(
                    await self.pool.fetchval("SELECT count(*) FROM studio_edge_invocation_logs WHERE project_id=$1 AND source='cron'", self.projects[0]),
                    1,
                )

                # Simulate due tick under advisory lock: executes once, advances next_run_at, second scan is a no-op.
                due_at = datetime(2026, 6, 15, 10, 5, 0, tzinfo=timezone.utc)
                await self.pool.execute(
                    'UPDATE project_edge_function_schedules SET next_run_at=$2 WHERE id=$1',
                    sched_id, due_at - timedelta(seconds=10),
                )
                async with self.pool.acquire() as holder:
                    locked = await holder.fetchval('SELECT pg_try_advisory_lock(hashtextextended($1, 0))', self.routes._SCHEDULE_LOCK_NAME)
                    self.assertTrue(locked)
                    try:
                        self.assertEqual(await self.routes.scan_edge_function_schedules(self.pool, now=due_at), 0)
                    finally:
                        await holder.fetchval('SELECT pg_advisory_unlock(hashtextextended($1, 0))', self.routes._SCHEDULE_LOCK_NAME)

                ran = await self.routes.scan_edge_function_schedules(self.pool, now=due_at)
                self.assertEqual(ran, 1)
                self.assertEqual(len(captured), 2)
                self.assertEqual(await self.routes.scan_edge_function_schedules(self.pool, now=due_at), 0)
                row_after = await self.pool.fetchrow('SELECT next_run_at, last_status FROM project_edge_function_schedules WHERE id=$1', sched_id)
                self.assertEqual(row_after['last_status'], 200)
                self.assertEqual(row_after['next_run_at'], datetime(2026, 6, 15, 10, 10, 0, tzinfo=timezone.utc))

                # Disabling Edge Functions disables active schedules automatically.
                await self.configure(False)
                self.assertFalse(await self.pool.fetchval('SELECT enabled FROM project_edge_function_schedules WHERE id=$1', sched_id))

                # Re-enable + re-enable schedule, then test unpublish disables it automatically.
                await self.configure(True)
                upd = await self.request('PUT', f'/my-function/schedules/{sched_id}', {'enabled': True, 'cron': '*/10 * * * *'})
                self.assertEqual(upd.status_code, 200, upd.text)
                self.assertEqual(upd.json()['schedule']['cron'], '*/10 * * * *')
                unpub = await self.request('POST', '/my-function/unpublish', {'revision': draft['revision'], 'expected_published_revision': draft['revision']})
                self.assertEqual(unpub.status_code, 200)
                self.assertFalse(await self.pool.fetchval('SELECT enabled FROM project_edge_function_schedules WHERE id=$1', sched_id))

                # Deleting paused schedule directly via DELETE endpoint, and deleting function cascades remaining schedule.
                paused_id = paused.json()['schedule']['id']
                self.assertEqual((await self.request('DELETE', f'/my-function/schedules/{paused_id}')).status_code, 200)
                del_fn = await self.request('DELETE', '/my-function', {'revision': draft['revision'], 'expected_published_revision': None})
                self.assertEqual(del_fn.status_code, 200)
                self.assertEqual(
                    await self.pool.fetchval("SELECT count(*) FROM project_edge_function_schedules WHERE project_id=$1 AND function_name='my-function'", self.projects[0]),
                    0,
                )

                # Project delete ON DELETE CASCADE removes any project schedules.
                f2 = (await self.request('PUT', '/cron-cascade', {'expected_revision': None, 'files': [{'name': 'index.ts', 'content': 'export {};'}]})).json()
                self.assertEqual((await self.request('POST', '/cron-cascade/publish', {'revision': f2['revision'], 'expected_published_revision': None})).status_code, 200)
                self.assertEqual((await self.request('POST', '/cron-cascade/schedules', {'name': 'on-proj', 'cron': '@hourly'})).status_code, 200)
                await self.pool.execute('DELETE FROM projects WHERE id=$1', self.projects[0])
                self.assertEqual(
                    await self.pool.fetchval('SELECT count(*) FROM project_edge_function_schedules WHERE project_id=$1', self.projects[0]),
                    0,
                )
        finally:
            server.shutdown()
            server.server_close()

    async def test_429_ack_clears_active_alert_persists_runtime_429_and_honors_timeout_and_body_cap(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock
        import httpx
        await self.configure(True)
        draft = await self.save()
        self.assertEqual((await self.publish(draft)).status_code, 200)

        t_first = datetime.now(timezone.utc) - timedelta(seconds=10)
        runtime_entry = {
            'id': 'rt-ext-429-1',
            'timestamp': t_first.isoformat(),
            'function_name': 'my-function',
            'level': 'warn',
            'source': 'worker',
            'message': 'Saturation: concurrency limit reached (2/2 project, 2/4 global)',
            'status': 429,
        }
        with patch.object(self.routes, '_fetch_merged_logs', AsyncMock(return_value={'logs': [runtime_entry], 'runtime_connected': True})):
            a1 = (await self.request('GET', '/alerts')).json()
            self.assertEqual(sum(1 for e in a1['events'] if e['kind'] == 'concurrency_429'), 1)
            self.assertTrue(any(a['kind'] == 'concurrency_429' and a['used'] == 1 for a in a1['active_alerts']), a1)
            a2 = (await self.request('GET', '/alerts')).json()
            self.assertEqual(sum(1 for e in a2['events'] if e['kind'] == 'concurrency_429'), 1)
            ack_id = next(e['id'] for e in a2['events'] if e['kind'] == 'concurrency_429')
            self.assertTrue((await self.request('POST', f'/alerts/{ack_id}/ack')).json()['acknowledged'])
            a3 = (await self.request('GET', '/alerts')).json()
            self.assertEqual([e for e in a3['events'] if e['kind'] == 'concurrency_429'], [])
            self.assertFalse(any(a['kind'] == 'concurrency_429' for a in a3['active_alerts']), a3)

        class MockStreamResp:
            status_code = 429
            headers = httpx.Headers({'content-type': 'application/json'})
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def aiter_bytes(self): yield b'{"code":"function_concurrency_limit"}'

        captured_timeouts = []
        class MockAsyncClient:
            def __init__(self, *, timeout, **kwargs):
                captured_timeouts.append(timeout)
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            def stream(self, *args, **kwargs): return MockStreamResp()

        with patch.object(self.routes.httpx, 'AsyncClient', MockAsyncClient), \
             patch.object(self.routes, '_fetch_merged_logs', AsyncMock(return_value={'logs': [], 'runtime_connected': True})):
            inv = await self.request('POST', '/my-function/invoke', {'method': 'GET', 'path': '/'})
            self.assertEqual(inv.status_code, 200)
            self.assertEqual(inv.json()['status'], 429)
            req_id = inv.json()['request_id']

        same_rt = {
            'id': 'rt-dup-429',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'function_name': 'my-function',
            'level': 'warn',
            'source': 'worker',
            'message': 'Saturation: concurrency limit reached',
            'status': 429,
            'request_id': req_id,
        }
        with patch.object(self.routes, '_fetch_merged_logs', AsyncMock(return_value={'logs': [same_rt], 'runtime_connected': True})):
            alerts_inv = (await self.request('GET', '/alerts')).json()
            evts = [e for e in alerts_inv['events'] if e['kind'] == 'concurrency_429']
            self.assertEqual(len(evts), 1, evts)
            self.assertTrue((await self.request('POST', f'/alerts/{evts[0]["id"]}/ack')).json()['acknowledged'])
            after_ack = (await self.request('GET', '/alerts')).json()
            self.assertFalse(any(a['kind'] == 'concurrency_429' for a in after_ack['active_alerts']), after_ack)

        await self.pool.execute("INSERT INTO user_groups(user_id,group_name,source) VALUES($1,'admin','test') ON CONFLICT DO NOTHING", self.users[0])
        raised = await self.request('PUT', '/quotas', {'worker_timeout_ms': 110_000})
        self.assertEqual(raised.status_code, 200, raised.text)
        captured_timeouts.clear()
        with patch.object(self.routes.httpx, 'AsyncClient', MockAsyncClient), \
             patch.object(self.routes, '_fetch_merged_logs', AsyncMock(return_value={'logs': [], 'runtime_connected': True})):
            await self.request('POST', '/my-function/invoke', {'method': 'GET', 'path': '/'})
        self.assertGreaterEqual(captured_timeouts[0].read, 115.0)
        nginx_conf = (ROOT / 'studio/nginx/nginx.conf').read_text(encoding='utf-8')
        self.assertIn('client_max_body_size 8m;', nginx_conf)

    async def test_npm_and_jsr_dependency_policy_bundle_publish_and_gc(self):
        from app import edge_bundler, edge_function_store as store, edge_functions
        await self.configure(True)
        for bad_files in (
            [{'name': 'index.ts', 'content': 'import x from "https://evil.example/mod.ts";'}],
            [{'name': 'index.ts', 'content': 'import x from "file:///etc/passwd";'}],
            [{'name': 'index.ts', 'content': 'import x from "../../etc/passwd";'}],
            [{'name': 'index.ts', 'content': 'export {};'}, {'name': 'deno.json', 'content': '{"imports":{"x":"http://127.0.0.1/x.ts"}}'}],
            [{'name': 'index.ts', 'content': 'export {};'}, {'name': 'bundle.eszip', 'content': 'bad'}],
        ):
            self.assertEqual((await self.request('PUT', '/pkg-bad', {'expected_revision': None, 'files': bad_files})).status_code, 400, bad_files)

        files_v1 = [
            {'name': 'deno.json', 'content': '{"imports":{"ms":"npm:ms@2.1.3","@std/fmt/bytes":"jsr:@std/fmt@1/bytes"}}'},
            {'name': 'index.ts', 'content': '// docs: https://example.com\nimport ms from "ms";\nimport { format } from "@std/fmt/bytes";\nDeno.serve(() => Response.json({ ms: ms("1h"), fmt: format(2048) }));\n'},
        ]
        saved = await self.request('PUT', '/pkg-fn', {'expected_revision': None, 'files': files_v1})
        self.assertEqual(saved.status_code, 200, saved.text)
        deps = saved.json()['dependencies']
        self.assertEqual(deps['npm'], ['npm:ms@2.1.3'])
        self.assertEqual(deps['jsr'], ['jsr:@std/fmt@1/bytes'])
        self.assertTrue(deps['requires_bundle'])
        self.assertFalse(deps['bundled'])

        fake_eszip = b'ESZIP2.3\x00\x00\x00\x04bundle-v1'
        bundler_mock = AsyncMock(return_value=fake_eszip)
        with patch.object(edge_bundler, 'bundle_function_eszip', bundler_mock):
            pub = await self.request('POST', '/pkg-fn/publish', {'revision': saved.json()['revision'], 'expected_published_revision': None})
        self.assertEqual(pub.status_code, 200, pub.text)
        bundler_mock.assert_awaited_once()
        self.assertTrue(pub.json()['dependencies']['bundled'])
        self.assertEqual(pub.json()['dependencies']['bundle_bytes'], len(fake_eszip))

        ctx = edge_functions.read_context(self.root, self.names[0], str(self.projects[0]))
        deployed_eszip = self.root / '.functions-runtime/code' / str(self.projects[0]) / ctx['revision'] / 'pkg-fn/bundle.eszip'
        self.assertEqual(deployed_eszip.read_bytes(), fake_eszip)

        with patch.object(edge_bundler, 'bundle_function_eszip', AsyncMock(side_effect=AssertionError('unexpected re-bundle'))):
            sec = await self.request('PUT', '/secrets', {'secrets': [{'name': 'API_KEY', 'value': 'val-1'}]})
        self.assertEqual(sec.status_code, 200, sec.text)

        files_v2 = [
            {'name': 'index.ts', 'content': 'import ms from "npm:ms@2.1.3"; Deno.serve(() => new Response(String(ms("2h"))));'},
        ]
        saved_v2 = (await self.request('PUT', '/pkg-fn', {'expected_revision': saved.json()['revision'], 'files': files_v2})).json()
        fake_eszip_v2 = b'ESZIP2.3\x00\x00\x00\x04bundle-v2'
        with patch.object(edge_bundler, 'bundle_function_eszip', AsyncMock(return_value=fake_eszip_v2)):
            bun_v2 = await self.request('POST', '/pkg-fn/bundle', {'revision': saved_v2['revision']})
        self.assertEqual(bun_v2.status_code, 200, bun_v2.text)
        self.assertTrue(bun_v2.json()['dependencies']['bundled'])
        saved_v3 = (await self.request('PUT', '/pkg-fn', {'expected_revision': saved_v2['revision'], 'files': [{'name': 'index.ts', 'content': 'Deno.serve(() => new Response("plain"))'}]})).json()
        gc_res = await self.request('POST', '/gc', {'min_age_seconds': 0})
        self.assertEqual(gc_res.status_code, 200, gc_res.text)
        state_now = store.load(self.root, self.names[0], str(self.projects[0]))
        self.assertTrue(store.has_bundle(self.root, state_now, 'pkg-fn', saved.json()['revision']))
        self.assertFalse(store.has_bundle(self.root, state_now, 'pkg-fn', saved_v2['revision']))
        self.assertEqual(saved_v3['dependencies']['requires_bundle'], False)

    async def test_private_package_registries_lifecycle_encryption_rbac_and_bundling(self):
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from app import edge_bundler

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'multitenant-test-ca')])
        now = datetime.now(timezone.utc)
        ca_pem = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
            .public_bytes(serialization.Encoding.PEM)
            .decode('ascii')
        )

        await self.configure(True, project=0, user=0)
        listed_user = await self.request('GET', '/registries', user=0)
        self.assertEqual(listed_user.status_code, 200, listed_user.text)
        self.assertEqual(listed_user.json()['registries'], [])
        self.assertFalse(listed_user.json()['limits']['can_configure_private_network'])

        # Non-global admin cannot set allow_private_network=True, ca_pem, private IPs, or http://.
        for payload, code in (
            ({'name': 'priv-1', 'kind': 'npm', 'registry_url': 'https://10.0.0.5/npm', 'auth_type': 'none', 'allow_private_network': True}, 403),
            ({'name': 'priv-ca', 'kind': 'npm', 'registry_url': 'https://npm.pkg.github.com', 'auth_type': 'none', 'ca_pem': ca_pem}, 403),
            ({'name': 'priv-ip', 'kind': 'npm', 'registry_url': 'https://10.0.0.5/npm', 'auth_type': 'none', 'allow_private_network': False}, 400),
            ({'name': 'priv-http', 'kind': 'npm', 'registry_url': 'http://npm.pkg.github.com', 'auth_type': 'none'}, 400),
        ):
            bad = await self.request('POST', '/registries', payload, user=0)
            self.assertEqual(bad.status_code, code, (payload, bad.status_code, bad.text))

        # Project admin creates public scoped npm registry encrypted with project DEK envelope.
        pub_res = await self.request('POST', '/registries', {
            'name': 'acme-npm',
            'kind': 'npm',
            'scope': '@acme',
            'registry_url': 'https://npm.pkg.github.com',
            'auth_type': 'bearer',
            'token': 'synthetic-gh-token',
            'enabled': True,
        }, user=0)
        self.assertEqual(pub_res.status_code, 200, pub_res.text)
        pub_reg = pub_res.json()['registry']
        self.assertTrue(pub_reg['has_token'])
        self.assertNotIn('synthetic-gh-token', pub_res.text)

        raw_cipher = await self.pool.fetchval(
            'SELECT token_ciphertext FROM project_edge_function_registries WHERE id=$1',
            uuid.UUID(pub_reg['id']),
        )
        self.assertTrue(raw_cipher and 'synthetic-gh-token' not in raw_cipher and raw_cipher.startswith('v2.'))

        dup_slot = await self.request('POST', '/registries', {
            'name': 'acme-npm-2',
            'kind': 'npm',
            'scope': '@acme',
            'registry_url': 'https://registry.example.org',
            'auth_type': 'none',
            'enabled': True,
        }, user=0)
        self.assertEqual(dup_slot.status_code, 409, dup_slot.text)

        jsr_disabled = await self.request('POST', '/registries', {
            'name': 'disabled-jsr',
            'kind': 'jsr',
            'registry_url': 'https://jsr.example.org',
            'auth_type': 'none',
            'enabled': False,
        }, user=0)
        self.assertEqual(jsr_disabled.status_code, 200, jsr_disabled.text)

        # Grant global admin to user 0 temporarily to configure private-network registry, then drop it to verify lock-down.
        await self.pool.execute("INSERT INTO user_groups(user_id,group_name,source) VALUES($1,'admin','test') ON CONFLICT DO NOTHING", self.users[0])
        listed_admin = await self.request('GET', '/registries', user=0)
        self.assertTrue(listed_admin.json()['limits']['can_configure_private_network'])

        priv_res = await self.request('POST', '/registries', {
            'name': 'corp-artifactory',
            'kind': 'npm',
            'scope': '',
            'registry_url': 'https://npm.corp.internal:8443/npm',
            'auth_type': 'basic',
            'token': 'ci-user:ci-pass-mt',
            'allow_private_network': True,
            'ca_pem': ca_pem,
            'enabled': True,
        }, user=0)
        self.assertEqual(priv_res.status_code, 200, priv_res.text)
        priv_reg = priv_res.json()['registry']
        self.assertTrue(priv_reg['allow_private_network'])
        self.assertTrue(priv_reg['has_custom_ca'])

        await self.pool.execute("DELETE FROM user_groups WHERE user_id=$1 AND group_name='admin'", self.users[0])
        for bad_update in (
            {'registry_url': 'https://169.254.169.254:8443/'},
            {'clear_ca_pem': True},
            {'ca_pem': ca_pem},
            {'allow_private_network': False},
        ):
            deny = await self.request('PUT', f"/registries/{priv_reg['id']}", bad_update, user=0)
            self.assertEqual(deny.status_code, 403, (bad_update, deny.status_code, deny.text))

        self.assertEqual((await self.request('PUT', f"/registries/{priv_reg['id']}", {'enabled': False}, user=0)).status_code, 200)
        self.assertEqual((await self.request('PUT', f"/registries/{priv_reg['id']}", {'enabled': True}, user=0)).status_code, 200)

        # Publish and forced ESZIP rebuild forward active decrypted registries excluding disabled ones.
        draft = (await self.request('PUT', '/priv-fn', {
            'expected_revision': None,
            'files': [{'name': 'index.ts', 'content': 'import x from "npm:@acme/tool@1.0.0"; Deno.serve(() => new Response(String(x)));'}],
        }, user=0)).json()
        fake_eszip_1 = b'ESZIP2.3\x00\x00\x00\x04mt-1'
        bundler_mock = AsyncMock(return_value=fake_eszip_1)
        with patch.object(edge_bundler, 'bundle_function_eszip', bundler_mock):
            pub = await self.request('POST', '/priv-fn/publish', {'revision': draft['revision'], 'expected_published_revision': None}, user=0)
        self.assertEqual(pub.status_code, 200, pub.text)
        passed_regs = bundler_mock.call_args.kwargs['registries']
        self.assertEqual({r['scope']: r['token'] for r in passed_regs}, {'@acme': 'synthetic-gh-token', '': 'ci-user:ci-pass-mt'})
        self.assertFalse(any(r['registry_url'] == 'https://jsr.example.org/' for r in passed_regs))

        with patch.object(edge_bundler, 'bundle_function_eszip', AsyncMock(side_effect=AssertionError('unexpected re-bundle'))):
            self.assertEqual((await self.request('POST', '/priv-fn/bundle', {'revision': draft['revision']}, user=0)).status_code, 200)

        self.assertEqual((await self.request('PUT', f"/registries/{pub_reg['id']}", {'token': 'ghp_mt_rotated'}, user=0)).status_code, 200)
        fake_eszip_2 = b'ESZIP2.3\x00\x00\x00\x04mt-2'
        rebuild_mock = AsyncMock(return_value=fake_eszip_2)
        with patch.object(edge_bundler, 'bundle_function_eszip', rebuild_mock):
            rebuilt = await self.request('POST', '/priv-fn/bundle', {'revision': draft['revision'], 'force': True}, user=0)
        self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
        self.assertEqual(rebuilt.json()['dependencies']['bundle_bytes'], len(fake_eszip_2))
        rebuilt_regs = rebuild_mock.call_args.kwargs['registries']
        self.assertEqual({r['scope']: r['token'] for r in rebuilt_regs}, {'@acme': 'ghp_mt_rotated', '': 'ci-user:ci-pass-mt'})

        # Project isolation & deletion + completed audit log.
        other_proj = await self.request('GET', '/registries', project=1, user=1)
        self.assertEqual(other_proj.json()['registries'], [])
        self.assertEqual((await self.request('DELETE', f"/registries/{jsr_disabled.json()['registry']['id']}", project=1, user=1)).status_code, 404)
        self.assertEqual((await self.request('DELETE', f"/registries/{jsr_disabled.json()['registry']['id']}", user=0)).status_code, 200)
        self.assertEqual((await self.request('DELETE', '/registries/bad-uuid', user=0)).status_code, 400)
        audit_counts = await self.pool.fetchrow(
            "SELECT count(*) FILTER (WHERE action='configure_registry' AND outcome='completed') AS cfg, "
            "count(*) FILTER (WHERE action='delete_registry' AND outcome='completed') AS del "
            'FROM studio_edge_audit'
        )
        self.assertGreaterEqual(audit_counts['cfg'], 4)
        self.assertEqual(audit_counts['del'], 1)

