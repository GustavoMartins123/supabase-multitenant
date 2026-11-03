"""Exercise Studio publication, opaque authorizer, gateways and runtime in disposable containers."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-image',required=True)
    parser.add_argument('--authorizer-image',required=True)
    parser.add_argument('--edge-image',default='supabase/edge-runtime:v1.74.2')
    parser.add_argument('--nginx-image',default='nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim')
    parser.add_argument('--gateway-image',required=True)
    parser.add_argument('--database-image',default='postgres:15')
    parser.add_argument('--redis-image',default='redis:8.8.0-alpine3.23')
    parser.add_argument('--rest-image',default='postgrest/postgrest:v16.5')
    parser.add_argument('--result',type=Path)
    parser.add_argument('--keep-fixture',action='store_true')
    args=parser.parse_args()
    prefix='functions-management-'+uuid.uuid4().hex[:8];names=[];checks=[]
    def docker(*command):return subprocess.check_output(['docker',*command],stderr=subprocess.PIPE,text=True).strip()
    def start(suffix,*options):
        name=prefix+'-'+suffix
        docker('run','-d','--pull=never','--name',name,'--label','functions.management-fixture=true','--network',prefix,*options)
        names.append(name);return name
    def mount(source,target,rw=False):return ['-v',str(source)+':'+target+(':rw' if rw else ':ro')]
    def port(name,number):
        info=json.loads(docker('inspect',name))[0]
        return info['NetworkSettings']['Ports'][str(number)+'/tcp'][0]['HostPort']
    def record(name):checks.append(name);print(name+': passed',flush=True)
    def wait(url,client,expected=200):
        for _ in range(120):
            try:
                r=client.get(url)
                if r.status_code==expected:return r
            except httpx.HTTPError:pass
            time.sleep(.25)
        raise RuntimeError('Fixture readiness failed: '+url)
    temporary=tempfile.TemporaryDirectory(prefix=prefix+'-');fixture=Path(temporary.name);fixture.chmod(0o755);server=fixture/'server';server.mkdir(mode=0o700)
    try:
        for image in (args.api_image,args.authorizer_image,args.edge_image,args.nginx_image,args.gateway_image,args.database_image,args.redis_image,args.rest_image):docker('image','inspect',image)
        docker('network','create','--label','functions.management-fixture=true',prefix)
        db=start('db','--network-alias','database','--tmpfs','/var/lib/postgresql/data:rw','-e','POSTGRES_PASSWORD=synthetic-test-password',args.database_image)
        for _ in range(100):
            if subprocess.run(['docker','exec',db,'pg_isready','-U','postgres'],capture_output=True).returncode==0:break
            time.sleep(.2)
        env={
            'FIXTURE_ADMIN_DSN':'postgres://postgres:synthetic-test-password@database:5432/postgres',
            'DB_DSN':'postgres://platform_app:'+'p'*32+'@database:5432/postgres',
            'META_ADMIN_DSN':'postgres://platform_meta_admin:'+'m'*32+'@database:5432/postgres',
            'PROJECT_SECRETS_MASTER_KEY':base64.urlsafe_b64encode(b'0'*32).decode(),
            'PG_META_CRYPTO_KEY':base64.urlsafe_b64encode(b'1'*32).decode(),
            'STUDIO_SERVICE_KEY_ENCRYPTION_KEY':base64.urlsafe_b64encode(b'2'*32).decode(),
            'NGINX_HMAC_SECRET':'n'*48,'STUDIO_GATEWAY_HMAC_SECRET':'1'*64,'PROJECTS_API_HMAC_SECRET':'2'*64,
            'LOGFLARE_PRIVATE_ACCESS_TOKEN':'synthetic-test-logflare','HOST_AGENT_HMAC_SECRET':'h'*32,
            'STUDIO_CACHE_INVALIDATION_URL':'http://functions-api:19090','STUDIO_CACHE_INVALIDATION_CA_FILE':'',
            'PYTHONPATH':'/workspace/servidor/api-internal:/workspace/tests/integration/fixtures','PYTHONDONTWRITEBYTECODE':'1',
        }
        options=[]
        for key,value in env.items():options+=['-e',key+'='+value]
        api=start('api','--network-alias','functions-api','--user',str(os.getuid())+':'+str(os.getgid()),'-p','127.0.0.1::18000',*options,
            *mount(ROOT,'/workspace'),*mount(fixture,'/fixture',True),'--entrypoint','uvicorn',args.api_image,'functions_management_api:app','--host','0.0.0.0','--port','18000','--no-access-log')
        with httpx.Client(trust_env=False,verify=False,timeout=25) as client:
            api_origin='http://127.0.0.1:'+port(api,18000);wait(api_origin+'/healthz',client)
            state=json.loads((fixture/'state.json').read_text());projects=state['projects']
            record('real_database_migrations_and_least_privilege_api_bootstrap')
            start('redis','--network-alias','traffic-redis',args.redis_image,'redis-server','--requirepass','r'*32)
            auth=start('authorizer','--network-alias','key-authorizer','-p','127.0.0.1::18010',
                '-e','DB_DSN=postgres://key_authorizer:'+'k'*32+'@database:5432/postgres','-e','ACCESS_ADMISSION_SECRET='+'a'*64,
                '-e','ACCESS_RATE_REDIS_PASSWORD='+'r'*32,'-e','ACCESS_ADMIN_CIDRS=127.0.0.1/32',
                *mount(ROOT/'servidor/key-authorizer/app.py','/app/app.py'),*mount(ROOT/'servidor/key-authorizer/admission.py','/app/admission.py'),
                *mount(ROOT/'servidor/api-internal/app/opaque_keys.py','/app/opaque_keys.py'),*mount(ROOT/'servidor/api-internal/app/access_policy.py','/app/access_policy.py'),args.authorizer_image)
            auth_origin='http://127.0.0.1:'+port(auth,18010);wait(auth_origin+'/healthz',client)
            runtime=start('runtime','--network-alias','functions','--user',str(os.getuid())+':'+str(os.getgid()),'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,size=128m',
                '-e','DENO_DIR=/tmp/deno','-p','127.0.0.1::9000',*mount(ROOT/'servidor/volumes/functions/main','/home/deno/main'),
                *mount(server/'.functions-runtime','/home/deno/runtime'),*mount(server/'.functions-tenants','/home/deno/tenant-config'),
                *mount(server/'.functions-hosts','/etc/hosts',True),args.edge_image,'start','--main-service','/home/deno/main')
            wait('http://127.0.0.1:'+port(runtime,9000)+'/__health',client)
            gateways={}
            for name,project in projects.items():
                start(name+'-rest','--network-alias','supabase-rest-'+name,
                    '-e','PGRST_DB_URI=postgres://authenticator:synthetic-rest-password@database:5432/_supabase_'+name,
                    '-e','PGRST_JWT_SECRET='+__import__('hashlib').sha256(name.encode()).hexdigest(),'-e','PGRST_DB_ANON_ROLE=anon',args.rest_image)
                template=(ROOT/'servidor/generateProject/nginxtemplate').read_text()
                mapping={'{{project_id}}':name,'{{project_public_ref}}':project['ref'],'{{project_uuid}}':project['id'],'{{server_url}}':'api.example.com',
                    '${ANON_KEY_PROJETO}':project['anon_jwt'],'${SERVICE_ROLE_KEY_PROJETO}':project['service_jwt'],
                    '${API_GATEWAY_TOKEN_PROJETO}':project['gateway_token'],'${FILE_SIZE_LIMIT}':'1000000','${SUPABASE_NETWORK_SUBNET}':'172.16.0.0/12'}
                for key,value in mapping.items():template=template.replace(key,value)
                path=fixture/(name+'.conf');path.write_text(template)
                gateway=start(name+'-nginx','--network-alias','supabase-nginx-'+name,'-p','127.0.0.1::8080',*mount(path,'/etc/nginx/nginx.conf'),args.nginx_image)
                gateways[name]='http://127.0.0.1:'+port(gateway,8080)
            certificate=fixture/'tls';certificate.mkdir()
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',str(certificate/'server.key'),'-out',str(certificate/'server.pem')],check=True,capture_output=True)
            for path in certificate.iterdir():path.chmod(0o644)
            edge_block=(ROOT/'studio/nginx/nginx.conf').read_text().split('        location ~ "^/api/platform/projects/(?<edge_ref>',1)[1].split('        location ~ "^/api/platform/projects/(?<content_ref>',1)[0]
            edge_block='location ~ "^/api/platform/projects/(?<edge_ref>'+edge_block
            config='''worker_processes 1; pid /tmp/nginx.pid; error_log /dev/stderr warn;
            env STUDIO_GATEWAY_HMAC_SECRET; env SERVER_DOMAIN; events {worker_connections 128;}
            http { access_log off; resolver 127.0.0.11 ipv6=off; lua_shared_dict internal_hmac_nonces 1m;
                lua_package_path "/workspace/studio/nginx/lua/?.lua;;";
                init_by_lua_block {
                    package.loaded["project_context.user_context_headers"] = {apply=function()
                        local login=ngx.var.cookie_user or ""
                        local r=require("resty.http").new():request_uri("http://functions-api:19090/session/"..login)
                        if not r or r.status~=200 then return ngx.exit(401) end
                        ngx.var.auth_user_token=require("cjson.safe").decode(r.body).token
                        ngx.req.set_header("X-User-Token",ngx.var.auth_user_token)
                    end}
                    package.loaded["project_context.studio_context"] = {load=function(ref)
                        if ref~=string.rep("a",20) and ref~=string.rep("b",20) then return nil,"Project not found",404 end
                        return {ref=ref,enc_admin_key="fixture-administrative-context"}
                    end}
                }
                server { listen 8443 ssl; ssl_certificate /config/tls/server.pem;ssl_certificate_key /config/tls/server.key;
                    set $authelia_email $cookie_user;set $authelia_groups active;
                    set $auth_user_id ""; set $auth_user_token ""; set $project_ref ""; set $server_path "";
                    set $server_domain http://functions-api:18000;set $server_hostname functions-api;set $backend_tls_name functions-api;
            '''+edge_block+'''
                location ~ "^/api/projects/[a-z]{20}/settings$" {
                    access_by_lua_file /workspace/studio/nginx/lua/security/studio_edge_access.lua;
                    proxy_set_header X-User-Token $auth_user_token;
                    proxy_pass http://functions-api:18000;
                }
                location ~* ^/api/(?:v1|platform)/projects/[^/]+/functions(?:/|$) { return 404; }
                location / { return 404; }
            }}'''
            (fixture/'studio.conf').write_text(config)
            # The production edge block uses its installed Lua path.
            gateway=start('studio','--network-alias','studio-gateway','-p','127.0.0.1::8443','-e','STUDIO_GATEWAY_HMAC_SECRET='+'1'*64,'-e','SERVER_DOMAIN=http://functions-api:18000',
                *mount(ROOT,'/workspace'),*mount(ROOT/'studio/nginx/lua/security/studio_edge_access.lua','/usr/local/openresty/lualib/security/studio_edge_access.lua'),
                *mount(fixture,'/config'),*mount(fixture/'studio.conf','/usr/local/openresty/nginx/conf/nginx.conf'),'--entrypoint','/usr/local/openresty/nginx/sbin/nginx',args.gateway_image,'-g','daemon off;')
            origin='https://localhost:'+port(gateway,8443);(fixture/'.studio-origin').write_text(origin)
            def management(method,suffix='',body=None,project='test_alpha',user='owner',headers=None):
                ref=projects[project]['ref']
                return client.request(method,origin+'/api/platform/projects/'+ref+'/edge-functions'+suffix,json=body,
                    headers={'Cookie':'user='+user,'Origin':origin,'X-Studio-Project-Ref':ref,**(headers or {})})
            def configure(enabled,project='test_alpha'):
                return client.put(origin+'/api/projects/'+projects[project]['ref']+'/settings',json={'settings':{'EDGE_FUNCTIONS_ENABLED':str(enabled).lower()}},headers={'Cookie':'user=owner','Origin':origin,'X-Studio-Project-Ref':projects[project]['ref']})
            code='''Deno.serve(async(req)=>{let data,status;try{const r=await fetch(Deno.env.get('SUPABASE_URL')+'/rest/v1/counter',{headers:{apikey:Deno.env.get('SUPABASE_SERVICE_ROLE_KEY'),Authorization:'Bearer '+Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')}});status=r.status;data=await r.json()}catch(e){data=e.name}let blocked=false;try{await fetch('http://postgres-meta-global:8080/query',{method:'POST',body:'{}'})}catch{blocked=true}return Response.json({version:'VERSION',ref:Deno.env.get('PROJECT_REF'),status,data,blocked,hasGlobalSecret:!!Deno.env.get('POSTGRES_PASSWORD'),hasJwtSecret:!!Deno.env.get('JWT_SECRET')})})'''
            def save(version,previous=None,project='test_alpha'):
                r=management('PUT','/my-function',{'expected_revision':previous,'files':[{'name':'index.ts','content':code.replace('VERSION',version)}]},project)
                assert r.status_code==200,r.text;return r.json()
            def publish(draft,project='test_alpha'):
                return management('POST','/my-function/publish',{'revision':draft['revision'],'expected_published_revision':draft['published_revision']},project)
            def invoke(project='test_alpha',key=None,headers=None,path='/my-function'):
                p=projects[project];key=p['publishable'] if key is None else key
                uri='/'+p['ref']+'/functions/v1'+path
                r=client.post(auth_origin+'/v1/admit',headers={'X-Admission-Secret':'a'*64},json={'project_ref':project,'gateway_token':p['gateway_token'],'uri':uri,'method':'GET','client_ip':'203.0.113.8','api_key':key,'authorization':'Bearer '+key})
                if r.status_code!=204:return r
                return client.get(gateways[project]+'/functions/v1'+path,headers={'apikey':key,'Authorization':'Bearer '+key,
                    'X-Gateway-Admission':r.headers['X-Gateway-Admission'],'X-Admission-URI':uri,'X-Admission-Method':'GET',**(headers or {})})
            wait(origin+'/api/platform/projects/'+projects['test_alpha']['ref']+'/edge-functions',client,401)
            assert management('GET').json()=={'enabled':False,'functions':[]}
            alpha=save('alpha-v1');assert publish(alpha).status_code==409
            assert invoke().status_code==404
            record('default_disabled_and_publication_cannot_enable_project')
            assert configure(True).status_code==200
            r=publish(alpha);assert r.status_code==200,r.text
            for _ in range(30):
                first=invoke()
                if first.status_code==200 and first.json().get('status')==200:break
                time.sleep(.25)
            assert first.status_code==200 and first.json()['data']==[{'project':'test_alpha','value':42}],first.text
            assert first.json()['blocked'] and not first.json()['hasGlobalSecret'] and not first.json()['hasJwtSecret'],first.text
            record('studio_signed_publication_public_opaque_invocation_and_real_own_project_rest_call')
            beta=save('beta-v1',project='test_beta');assert configure(True,'test_beta').status_code==200
            assert publish(beta,'test_beta').status_code==200
            b=invoke('test_beta');assert b.status_code==200 and b.json()['data']==[{'project':'test_beta','value':42}],b.text
            record('same_function_name_has_independent_code_keys_and_database_for_each_project')
            changed=save('alpha-v2',alpha['revision']);assert invoke().json()['version']=='alpha-v1'
            assert publish(changed).status_code==200
            assert invoke().json()['version']=='alpha-v2' and invoke('test_beta').json()['version']=='beta-v1'
            record('draft_save_does_not_change_runtime_and_publication_affects_only_selected_project')
            assert invoke(key=projects['test_beta']['publishable']).status_code==403
            assert invoke(headers={'X-Project-Ref':projects['test_beta']['ref'],'X-Project-Name':'test_beta','X-Project-UUID':projects['test_beta']['id']}).json()['ref']==projects['test_alpha']['ref']
            for user in ('member','outsider'):
                assert management('GET',user=user).status_code==403
                assert management('POST','/my-function/publish',{'revision':changed['revision'],'expected_published_revision':changed['published_revision']},user=user).status_code==403
            assert management('GET',headers={'X-Studio-Project-Ref':projects['test_beta']['ref']}).status_code==409
            assert management('PUT','/forged',{'expected_revision':None,'files':[{'name':'index.ts','content':''}]},headers={'Origin':'https://attacker.invalid'}).status_code==403
            assert client.get(api_origin+'/api/projects/'+projects['test_alpha']['ref']+'/edge-functions').status_code==401
            assert client.post(origin+'/api/v1/projects/'+projects['test_alpha']['ref']+'/functions/deploy',headers={'Cookie':'user=owner'}).status_code==404
            record('cross_project_keys_forged_headers_members_csrf_unsigned_backend_and_legacy_deploy_denied')
            internal=json.loads((server/'.functions-runtime/tenants/test_alpha.json').read_text())['env']['SUPABASE_SERVICE_ROLE_KEY']
            for key in (projects['test_alpha']['publishable'],projects['test_alpha']['secret']):
                r=client.get(gateways['test_alpha']+'/rest/v1/counter',headers={'apikey':key,'Authorization':'Bearer '+key})
                assert r.status_code in {401,403},r.text
            assert client.get(gateways['test_beta']+'/rest/v1/counter',headers={'apikey':internal,'Authorization':'Bearer '+internal}).status_code==403
            assert invoke(key=internal).status_code==403
            record('private_runtime_keys_do_not_bypass_project_or_public_admission_boundary')
            assert configure(False).status_code==200
            assert invoke().status_code==404 and invoke('test_beta').status_code==200
            assert publish(changed).status_code==409
            assert client.get(gateways['test_alpha']+'/rest/v1/counter',headers={'apikey':internal,'Authorization':'Bearer '+internal}).status_code==403
            assert configure(True).status_code==200 and invoke().json()['version']=='alpha-v2'
            record('disable_revokes_invocation_publication_and_internal_credentials_only_for_selected_project')
            projection=server/'.functions-tenants/test_alpha.json';original=projection.read_bytes();projection.unlink()
            assert invoke().status_code==503 and invoke('test_beta').status_code==200
            projection.write_bytes(original)
            context=server/'.functions-runtime/tenants/test_alpha.json';original=context.read_bytes()
            context.write_bytes((server/'.functions-runtime/tenants/test_beta.json').read_bytes())
            assert invoke().status_code==503 and invoke('test_beta').status_code==200
            context.write_bytes(original)
            assert invoke(path='/hello').status_code==404
            record('lifecycle_withdrawal_context_substitution_and_shared_source_fallback_fail_closed')
            for container in (api,runtime):
                info=json.loads(docker('inspect',container))[0]
                assert not any(m['Destination']=='/var/run/docker.sock' for m in info['Mounts'])
            record('management_api_and_global_runtime_have_no_docker_socket')
            if args.result:args.result.write_text(json.dumps({'checks':checks,'fixture':str(fixture),'origin':origin,'containers':names},indent=2))
            print('Completed '+str(len(checks))+' full Functions management checks.',flush=True)
            if args.keep_fixture:
                (fixture/'ready.json').write_text(json.dumps({'origin':origin,'api_origin':api_origin,'authorizer_origin':auth_origin,'gateways':gateways,'containers':names,'network':prefix}))
                print('Retained fixture: '+str(fixture),flush=True)
                temporary._finalizer.detach();return
    except Exception:
        for name in names:
            log=subprocess.run(['docker','logs','--tail','60',name],capture_output=True,text=True)
            output=log.stdout+log.stderr
            print(name+' logs: '+output[-2000:],flush=True)
            (Path('/tmp')/(name+'.log')).write_text(output)
        raise
    finally:
        if not args.keep_fixture or not (fixture/'ready.json').exists():
            for name in reversed(names):subprocess.run(['docker','rm','-f','-v',name],capture_output=True)
            subprocess.run(['docker','network','rm',prefix],capture_output=True)
            temporary.cleanup()

if __name__=='__main__':main()
