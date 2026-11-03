"""Function publication and credentials against disposable PostgreSQL databases."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch
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
            return {'db_user_id':row['id'],'is_global_admin':False}
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

    async def test_activation_drafts_publication_and_disable_are_independent(self):
        listing=await self.request('GET');self.assertEqual(listing.json(),{'enabled':False,'functions':[]})
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
        for method,path,body in [('GET','',None),('PUT','/my-function',{'expected_revision':None,'files':[{'name':'index.ts','content':''}]}),('POST','/my-function/publish',{'revision':'a'*64,'expected_published_revision':None})]:
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
        self.assertEqual(listing.json(),{'enabled':False,'functions':[]})
        self.assertEqual((await self.publish(draft)).status_code,409)
