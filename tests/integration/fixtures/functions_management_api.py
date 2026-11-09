"""Disposable integration fixture. Privileged bootstrap never ships in the API."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

import asyncpg
from fastapi import FastAPI,Depends,Request
from app import database
from app.internal_service_auth import InternalServiceAuthenticationMiddleware
from app.routers import studio_edge_functions as routes
if not Path(routes.__file__).resolve().is_relative_to(Path('/workspace/servidor/api-internal')):
    raise RuntimeError('Function fixture must load the mounted API source')
from app.project_settings import _normalize_settings_updates
from app.schemas import UpdateSettings

FIXTURE=Path('/fixture')
routes.ROOT=FIXTURE/'server'
app=FastAPI()
app.include_router(routes.router)
app.add_middleware(InternalServiceAuthenticationMiddleware)


def encode(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=').decode()
def user_token(user,state):
    value=encode({'sub':user,'iat':int(time.time()),'exp':int(time.time())+120,'aud':'projects-api','directory_revision':state['directory']['revision']})
    return 'v1.'+value+'.'+hmac.new(os.environ['NGINX_HMAC_SECRET'].encode(),value.encode(),hashlib.sha256).hexdigest()
def project_jwt(name,role):
    data=encode({'alg':'HS256','typ':'JWT'})+'.'+encode({'role':role,'exp':int(time.time())+86400})
    return data+'.'+base64.urlsafe_b64encode(hmac.new(hashlib.sha256(name.encode()).hexdigest().encode(),data.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()


class Directory(BaseHTTPRequestHandler):
    def do_GET(self):
        state=json.loads((FIXTURE/'state.json').read_text())
        if self.path.startswith('/session/'):
            login=self.path.split('/')[-1]
            if login not in state['users']:
                self.send_error(401);return
            body=json.dumps({'token':user_token(state['users'][login],state)}).encode()
            self.send_response(200);self.end_headers();self.wfile.write(body);return
        if self.path!='/internal/users/directory':
            self.send_error(404);return
        from app.internal_hmac import verify_internal_hmac_signature
        nonce=self.headers.get('X-Internal-Nonce','')
        valid=verify_internal_hmac_signature(os.environ['PROJECTS_API_HMAC_SECRET'],service='projects-api',method='GET',target=self.path,
            body=b'',timestamp=int(self.headers.get('X-Internal-Timestamp','0')),nonce=nonce,signature=self.headers.get('X-Internal-Signature',''))
        if not valid:
            self.send_error(403);return
        body=json.dumps(state['directory'],separators=(',',':')).encode()
        signature=hmac.new(os.environ['PROJECTS_API_HMAC_SECRET'].encode(),b'studio-directory-v1\n'+nonce.encode()+b'\n'+body,hashlib.sha256).hexdigest()
        self.send_response(200);self.send_header('X-Directory-Signature',signature);self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass


@app.get('/healthz')
async def health():return {'status':'ok'}


@app.put('/api/projects/{ref}/settings')
async def settings(ref:str,body:UpdateSettings,request:Request,pool=Depends(database.get_pool)):
    await routes.configure_project(ref,_normalize_settings_updates(body.settings),request,pool)
    return {'status':'updated'}


@app.on_event('startup')
async def startup():
    from app.schema_migrations import apply_migrations
    from app.control_plane_roles import ensure_key_authorizer_role,ensure_platform_app_role,ensure_tenant_meta_roles
    from app.directory_service import DirectorySnapshot,reconcile_directory
    from app.opaque_keys import generate_opaque_key
    admin=await asyncpg.create_pool(os.environ['FIXTURE_ADMIN_DSN'],min_size=1,max_size=4)
    async with admin.acquire() as conn:
        await apply_migrations(conn)
    state={'users':{name:str(uuid.uuid4()) for name in ('owner','member','outsider')},'projects':{}}
    directory={'sequence':1,'revision':'a'*64,'users':[
        {'id':value,'username':name,'display_name':name,'groups':['active'],'is_active':True,'source':{'source':'fixture','email':name+'@example.test'}}
        for name,value in state['users'].items()]}
    state['directory']=directory
    async with admin.acquire() as conn:
        async with conn.transaction():await reconcile_directory(conn,DirectorySnapshot.model_validate(directory))
        for index,name in enumerate(('test_alpha','test_beta')):
            project_id=uuid.uuid4();ref=chr(97+index)*20;gateway_token=hashlib.sha256((name+'gateway').encode()).hexdigest()
            await conn.execute('''INSERT INTO projects(id,name,display_name,public_ref,owner_id,api_gateway_token_hash,opaque_keys_activated_at,opaque_gateway_ready_at)
                VALUES($1,$2,$2,$3,$4,$5,now(),now())''',project_id,name,ref,uuid.UUID(state['users']['owner']),hashlib.sha256(gateway_token.encode()).digest())
            await conn.execute("INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'admin'),($1,$3,'member')",project_id,uuid.UUID(state['users']['owner']),uuid.UUID(state['users']['member']))
            material={'id':str(project_id),'name':name,'ref':ref,'gateway_token':gateway_token,
                      'anon_jwt':project_jwt(name,'anon'),'service_jwt':project_jwt(name,'service_role')}
            for kind in ('publishable','secret'):
                key=generate_opaque_key(project_id,kind);slot=uuid.uuid4()
                await conn.execute("INSERT INTO project_api_key_slots(id,project_id,name,kind,allowed_services,automatic_rotation_enabled,application_ref) VALUES($1,$2,$3,$4,$5,false,$6)",slot,project_id,kind,kind,['rest','functions'],chr(120+index)*20 if kind=='publishable' else None)
                await conn.execute("INSERT INTO project_api_keys(id,slot_id,secret_hash,token_hint,status,activated_at) VALUES($1,$2,$3,$4,'active',now())",uuid.uuid4(),slot,key.digest,key.token_hint)
                material[kind]=key.token
            state['projects'][name]=material
            path=routes.ROOT/'projects'/name;path.mkdir(parents=True)
            values={'PROJECT_ID':name,'PROJECT_UUID':str(project_id),'PROJECT_PUBLIC_REF':ref,'ANON_KEY_PROJETO':material['anon_jwt'],
                    'SERVICE_ROLE_KEY_PROJETO':material['service_jwt'],'JWT_SECRET_PROJETO':hashlib.sha256(name.encode()).hexdigest(),'API_EXTERNAL_URL':'https://api.example.com/'+ref}
            (path/'.env').write_text('\n'.join(key+'='+value for key,value in values.items())+'\n')
            await conn.execute('CREATE DATABASE "_supabase_'+name+'"')
        for role in ('anon','authenticated','service_role'):
            await conn.execute('CREATE ROLE '+role+' NOLOGIN')
        await conn.execute("CREATE ROLE authenticator LOGIN NOINHERIT PASSWORD 'synthetic-rest-password'")
        await conn.execute('GRANT anon,authenticated,service_role TO authenticator')
    for name in state['projects']:
        conn=await asyncpg.connect(os.environ['FIXTURE_ADMIN_DSN'].rsplit('/',1)[0]+'/_supabase_'+name)
        await conn.execute('CREATE TABLE public.counter(project text,value int)')
        await conn.execute('INSERT INTO public.counter VALUES($1,42)',name)
        await conn.execute('GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;GRANT SELECT ON public.counter TO anon,authenticated,service_role')
        await conn.close()
    await ensure_tenant_meta_roles(admin,admin_dsn=os.environ['FIXTURE_ADMIN_DSN'],password='m'*32)
    async with admin.acquire() as conn:
        for name in state['projects']:await conn.execute('GRANT CONNECT ON DATABASE "_supabase_'+name+'" TO authenticator')
    await ensure_key_authorizer_role(admin,password='k'*32)
    await ensure_platform_app_role(admin,password='p'*32)
    await admin.close()
    sys.path.insert(0,'/workspace/servidor/generateProject')
    import functions_config
    functions_config.sync(routes.ROOT)
    (FIXTURE/'state.json').write_text(json.dumps(state));(FIXTURE/'state.json').chmod(0o600)
    threading.Thread(target=ThreadingHTTPServer(('0.0.0.0',19090),Directory).serve_forever,daemon=True).start()
    await database.initialize_pool(os.environ['DB_DSN'])


@app.on_event('shutdown')
async def shutdown():await database.close_pool()
