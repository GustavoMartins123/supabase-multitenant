"""Exercise native worker network permissions using synthetic HTTP peers."""
from __future__ import annotations
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
import httpx

CANARY = '''from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  with Path('/fixture/hits').open('a') as f:f.write(self.headers.get('Host','')+' '+self.path+'\\n')
  if self.path.startswith('/redirect'):
   self.send_response(302);self.send_header('Location','http://metadata.internal.example.com:8080/forbidden-redirect');self.end_headers();return
  code=self.path.endswith('.ts')
  body=b'export const marker="approved-module";' if code else b'{"synthetic":true}'
  self.send_response(200);self.send_header('Content-Type','application/typescript' if code else 'application/json');self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
HTTPServer(('0.0.0.0',8080),H).serve_forever()
'''
PROBE = '''import net from 'node:net';
Deno.serve(async(req)=>{const url=new URL(req.url);const target=url.searchParams.get('target');const kind=url.searchParams.get('kind');try{
 if(kind==='hosts'){await Deno.writeTextFile('/etc/hosts','127.0.0.1 example.com');return Response.json({allowed:true})}
 if(kind==='tcp'){const u=new URL(target);const conn=await Deno.connect({hostname:u.hostname,port:Number(u.port)});conn.close();return Response.json({allowed:true})}
 if(kind==='node'){const u=new URL(target);await new Promise((resolve,reject)=>{const socket=net.connect({host:u.hostname,port:Number(u.port)});socket.on('connect',()=>{socket.destroy();resolve(true)});socket.on('error',reject)});return Response.json({allowed:true})}
 if(kind==='request'){await Deno.permissions.request({name:'net',host:new URL(target).host});const r=await fetch(target,{signal:AbortSignal.timeout(1500)});await r.body?.cancel();return Response.json({allowed:true,status:r.status})}
 if(kind==='proxy'){const client=Deno.createHttpClient({proxy:{url:target}});try{const r=await fetch(Deno.env.get('SUPABASE_URL')+'/proxy-target',{client,signal:AbortSignal.timeout(1500)});await r.body?.cancel();return Response.json({allowed:true,status:r.status})}finally{client.close()}}
 const r=await fetch(target,{signal:AbortSignal.timeout(1500)});await r.body?.cancel();return Response.json({allowed:true,status:r.status})
 }catch(error){return Response.json({allowed:false,error:error.name})}})
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--supervisor',type=Path,required=True)
 parser.add_argument('--contract',choices=['versioned','projected'],required=True)
 parser.add_argument('--edge-image',required=True)
 parser.add_argument('--python-image',default='servidor-projects-api:latest')
 parser.add_argument('--result',type=Path)
 args=parser.parse_args()
 prefix='functions-net-test-'+uuid.uuid4().hex[:8];network=prefix;names=[];checks=[]
 def docker(*command):return subprocess.check_output(['docker',*command],stderr=subprocess.PIPE,text=True).strip()
 def record(name):checks.append(name);print(name+': passed',flush=True)
 def token(project):
  def enc(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
  signed=enc(b'{"alg":"HS256","typ":"JWT"}')+'.'+enc(json.dumps({'role':'anon','exp':int(time.time())+600}).encode())
  return signed+'.'+enc(hmac.new((project+'-synthetic-secret').encode(),signed.encode(),hashlib.sha256).digest())
 identities={'test_alpha':'11111111-1111-4111-8111-111111111111','test_beta':'22222222-2222-4222-8222-222222222222'}
 refs={'test_alpha':'a'*20,'test_beta':'b'*20}
 tokens={project:token(project) for project in identities}
 with tempfile.TemporaryDirectory(prefix=prefix+'-') as temporary:
  fixture=Path(temporary);code=fixture/'code';code.mkdir();shutil.copytree(args.supervisor,code/'main');(code/'probe').mkdir();(code/'probe/index.ts').write_text(PROBE)
  (fixture/'canary.py').write_text(CANARY);(fixture/'hits').write_text('')
  hosts=fixture/'hosts';hosts.write_text('127.0.0.1 localhost\n::1 localhost\n');hosts.chmod(0o666)
  config=fixture/'config';config.mkdir();runtime=fixture/'runtime';(runtime/'tenants').mkdir(parents=True)
  def context(project,external=None):
   allow=[] if external is None else external
   if args.contract=='projected':
    value={'project_ref':refs[project],'technical_name':project,'project_uuid':identities[project],
           'anon_key':tokens[project],'service_role_key':'synthetic-service-'+project,'jwt_secret':project+'-synthetic-secret','network_allowlist':[]}
    path=config/(project+'.json');path.write_text(json.dumps(value))
   value={'project':project,'uuid':identities[project],'jwt_secret':project+'-synthetic-secret','revision':'1'*64,'network_allowlist':allow,
          'env':{'SUPABASE_URL':'http://supabase-nginx-'+project+':8080','SUPABASE_PUBLIC_URL':'https://project.example.com',
                 'SUPABASE_ANON_KEY':'sb_publishable_synthetic-'+project,'SUPABASE_SERVICE_ROLE_KEY':'sb_secret_synthetic-'+project,
                 'SUPABASE_DB_URL':'postgres://synthetic:synthetic@database:5432/_supabase_'+project}}
   if args.contract=='versioned':value['env']['SUPABASE_ANON_KEY']=tokens[project]
   path=runtime/'tenants'/(project+'.json')
   dest=runtime/'code'/(identities[project] if args.contract=='projected' else project)/('1'*64);dest.mkdir(parents=True,exist_ok=True)
   for name in ['probe','module']:
    target=dest/name
    if target.exists():shutil.rmtree(target)
    shutil.copytree(code/name,target)
   name=path.with_suffix('.tmp');name.write_text(json.dumps(value));name.replace(path)
  (code/'module').mkdir();(code/'module/index.ts').write_text('import {encode} from "https://deno.land/std@0.131.0/encoding/base64.ts";Deno.serve(()=>Response.json({marker:atob(encode("approved-module"))}));')
  try:
   docker('network','create','--label','functions.security-fixture=true',network)
   canary=prefix+'-http';command=['run','-d','--name',canary,'--label','functions.security-fixture=true','--network',network,
        '--user',str(os.getuid())+':'+str(os.getgid()),'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m']
   for alias in ['supabase-nginx-test_alpha','supabase-nginx-test_beta','metadata.internal.example.com','api.allowed.example.com']:
    command+=['--network-alias',alias]
   command+=['-v',str(fixture)+':/fixture:rw','--entrypoint','python',args.python_image,'/fixture/canary.py'];docker(*command);names.append(canary)
   for project in identities:context(project)
   container=prefix+'-runtime';command=['run','-d','--name',container,'--label','functions.security-fixture=true','--network',network,'-e','DENO_DIR=/tmp/deno','-e','VERIFY_JWT=true','--memory','768m','-v',str(hosts)+':/etc/hosts:rw','-p','127.0.0.1::9000']
   command+=['--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,size=128m']
   command+=['-v',str(code/'main')+':/home/deno/main:ro','-v',str(runtime)+':/home/deno/runtime:ro'];main_path='/home/deno/main'
   if args.contract=='projected':command+=['-v',str(config)+':/home/deno/tenant-config:ro']
   command+=[args.edge_image,'start','--main-service',main_path];docker(*command);names.append(container)
   info=json.loads(docker('inspect',container))[0];port=info['NetworkSettings']['Ports']['9000/tcp'][0]['HostPort'];origin='http://127.0.0.1:'+port
   ip=docker('exec',canary,'python','-c','import socket;print(socket.gethostbyname(socket.gethostname()))')
   assert ip and ip != '127.0.0.1', 'Canary requires a real private network address'
   with httpx.Client(trust_env=False,timeout=25) as client:
    def call(project,target,kind='fetch',function='probe'):
     headers={'Authorization':'Bearer '+tokens[project],'apikey':tokens[project],'X-Project-Name':project,'X-Project-Ref':refs[project],'X-Project-UUID':identities[project]}
     return client.get(origin+'/'+function,headers=headers,params={'target':target,'kind':kind})
    own='http://supabase-nginx-test_alpha:8080/own'
    for attempt in range(60):
     try:
      response=call('test_alpha',own)
      if response.status_code==200:break
     except httpx.TransportError:pass
     time.sleep(0.2)
    assert response.status_code==200,response.text
    assert response.json()['allowed'] and response.json()['status']==200;record('own_project_http_works')
    blocked={'other_project':'http://supabase-nginx-test_beta:8080/other','administrative_service':'http://metadata.internal.example.com:8080/admin',
             'private_ip':'http://'+ip+':8080/direct-ip','loopback':'http://127.0.0.1:9000/host','cloud_metadata':'http://169.254.169.254/latest/meta-data/',
             'unapproved_api':'https://example.com/'}
    for label,target in blocked.items():
     response=call('test_alpha',target);assert response.status_code==200 and response.json().get('allowed') is False,(label,response.text);record(label+'_blocked')
    for kind in ['tcp','node','proxy','request','hosts']:
     response=call('test_alpha',blocked['administrative_service'],kind);assert response.status_code==200 and response.json().get('allowed') is False,(kind,response.text);record(kind+'_cannot_bypass_network_policy')
    response=call('test_alpha','http://supabase-nginx-test_alpha:8080/redirect');assert not response.json()['allowed'];record('redirect_to_internal_service_blocked')
    response=call('test_alpha','',function='module');assert response.status_code==500;record('unapproved_static_import_blocked')
    assert not any('api.allowed.example.com' in line or 'metadata.internal.example.com' in line for line in (fixture/'hits').read_text().splitlines()),'Blocked target was contacted'
    context('test_alpha',['api.allowed.example.com:8080'])
    response=call('test_alpha','http://api.allowed.example.com:8080/dns-private');assert response.status_code==500;record('approved_hostname_resolving_to_private_ip_blocked')
    context('test_alpha',['deno.land:443','example.com:443'])
    response=call('test_alpha','https://example.com/');assert response.json().get('allowed') and response.json().get('status')==200,response.text;record('explicit_api_grant_works')
    response=call('test_beta','https://example.com/');assert not response.json()['allowed'];record('api_grant_does_not_leak_to_other_project')
    response=call('test_alpha','',function='module');assert response.status_code==200 and response.json()=={'marker':'approved-module'},response.text;record('explicitly_approved_static_import_works')
    docker('network','disconnect',network,canary)
    aliases=['--alias', 'example.com']
    for alias in ['supabase-nginx-test_alpha','supabase-nginx-test_beta','metadata.internal.example.com','api.allowed.example.com']:aliases += ['--alias',alias]
    docker('network','connect',*aliases,network,canary)
    response=call('test_alpha','https://example.com/');assert response.status_code==200 and response.json().get('allowed') and response.json().get('status')==200,response.text;record('public_dns_pin_survives_private_dns_rebinding')
    context('test_alpha',[])
    response=call('test_alpha','https://example.com/');assert not response.json()['allowed'];record('network_grant_revocation_takes_effect')
    if args.result:args.result.write_text(json.dumps({'contract':args.contract,'image':args.edge_image,'checks':checks},indent=2))
   print('Completed '+str(len(checks))+' native worker network checks.',flush=True)
  finally:
   for name in reversed(names):subprocess.run(['docker','rm','-f','-v',name],capture_output=True)
   subprocess.run(['docker','network','rm',network],capture_output=True)

if __name__=='__main__':main()
