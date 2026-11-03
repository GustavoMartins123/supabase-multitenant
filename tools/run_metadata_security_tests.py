import argparse
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))
from app.pg_meta_crypto import encrypt_postgres_meta_uri, postgres_meta_authorization

parser=argparse.ArgumentParser(description='Verify metadata authentication and tenant connections in disposable containers.')
parser.add_argument('--metadata-image', action='append', required=True)
parser.add_argument('--postgres-image', default='postgres:15')
parser.add_argument('--result', type=Path)
args=parser.parse_args()
prefix='meta-auth-probe-'+uuid.uuid4().hex[:8]
network=prefix;db=prefix+'-db';names=[];reports={}
key=secrets.token_urlsafe(24)[:27];password=secrets.token_hex(16)
def docker(*args):
 return subprocess.check_output(['docker',*args],stderr=subprocess.PIPE,text=True).strip()
try:
 docker('network','create','--label','studio.metadata-security=true',network)
 docker('run','-d','--name',db,'--label','studio.metadata-security=true','--network',network,
        '--network-alias','db','-e','POSTGRES_PASSWORD='+password,args.postgres_image);names.append(db)
 for attempt in range(50):
  r=subprocess.run(['docker','exec',db,'pg_isready','-U','postgres'],capture_output=True)
  if r.returncode==0:break
  time.sleep(0.2)
 sql="""CREATE ROLE meta_guest LOGIN PASSWORD 'synthetic-meta';
 CREATE ROLE alpha LOGIN PASSWORD 'synthetic-alpha';
 CREATE ROLE beta LOGIN PASSWORD 'synthetic-beta';
 CREATE DATABASE meta_trap;
 CREATE DATABASE alpha;
 CREATE DATABASE beta;
 REVOKE CONNECT ON DATABASE alpha,beta,postgres FROM PUBLIC;
 GRANT CONNECT ON DATABASE alpha TO alpha;
 GRANT CONNECT ON DATABASE beta TO beta;
 GRANT CONNECT ON DATABASE meta_trap TO meta_guest;"""
 subprocess.run(['docker','exec','-i',db,'psql','-U','postgres','-v','ON_ERROR_STOP=1'],input=sql,text=True,check=True,capture_output=True)
 for version in args.metadata_image:
  name=prefix+'-meta-'+str(len(names))
  docker('run','-d','--name',name,'--label','studio.metadata-security=true','--network',network,
         '-e','PG_META_PORT=8080','-e','PG_META_DB_HOST=db','-e','PG_META_DB_NAME=meta_trap',
         '-e','PG_META_DB_USER=meta_guest','-e','PG_META_DB_PASSWORD=synthetic-meta','-e','CRYPTO_KEY='+key,
         '-p','127.0.0.1::8080','-p','127.0.0.1::8081',version);names.append(name)
  info=json.loads(docker('inspect',name))[0];port=info['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort'];admin_port=info['NetworkSettings']['Ports']['8081/tcp'][0]['HostPort'];origin='http://127.0.0.1:'+port
  checks=[]
  with httpx.Client(trust_env=False,timeout=10) as client:
   for attempt in range(50):
    try:
     r=client.get(origin+'/health')
     if r.status_code==401:break
    except httpx.TransportError:pass
    time.sleep(0.2)
   def check(label,response,status):
    assert response.status_code==status,(version,label,response.status_code,response.text[:200]);checks.append(label)
   for path in ['/','/health','/tables','/query','/generators/typescript','/does-not-exist']:
    check('unauthenticated_'+path,client.get(origin+path),401)
   check('unauthenticated_sql',client.post(origin+'/query',json={'query':'select 1'}),401)
   check('forged_credential',client.post(origin+'/query',headers={'Authorization':'Bearer '+'0'*64},json={'query':'select 1'}),401)
   check('public_project_key_is_not_metadata_auth',client.get(origin+'/health',headers={'Authorization':'Bearer synthetic-anon'}),401)
   auth={'Authorization':postgres_meta_authorization(key)}
   check('authenticated_health',client.get(origin+'/health',headers=auth),200)
   for encrypted in [None,'','invalid']:
    headers={**auth,**({'x-connection-encrypted':encrypted} if encrypted is not None else {})}
    check('no_fallback_connection_'+str(encrypted),client.post(origin+'/query',headers=headers,json={'query':'select current_database()'}),400)
   for project in ['alpha','beta']:
    dsn='postgres://'+project+':synthetic-'+project+'@db:5432/'+project
    headers={**auth,'x-connection-encrypted':encrypt_postgres_meta_uri(dsn,key)}
    response=client.post(origin+'/query',headers=headers,json={'query':"SELECT current_database() AS database,current_user AS role,has_database_privilege(current_user,'"+('beta' if project=='alpha' else 'alpha')+"','CONNECT') AS can_connect_other"})
    check('authorized_'+project+'_query',response,200)
    assert response.json()==[{'database':project,'role':project,'can_connect_other':False}]
   metrics='http://127.0.0.1:'+admin_port+'/metrics'
   check('administrative_metrics_require_auth',client.get(metrics),401)
   check('authorized_administrative_metrics',client.get(metrics,headers=auth),200)
  health=subprocess.run(['docker','exec',name,'node','/usr/src/app/security/healthcheck.mjs'],capture_output=True,text=True)
  assert health.returncode==0,'Authenticated image healthcheck failed'
  checks.append('authenticated_docker_healthcheck')
  logs=subprocess.run(['docker','logs',name],capture_output=True,text=True);log=logs.stdout+logs.stderr
  assert key not in log and postgres_meta_authorization(key) not in log
  checks.append('authentication_credentials_not_logged')
  reports[version]=checks;print(version+': '+str(len(checks))+' metadata HTTP and tenant checks passed',flush=True)
 if args.result:args.result.write_text(json.dumps(reports,indent=2))
finally:
 for name in reversed(names):subprocess.run(['docker','rm','-f','-v',name],capture_output=True)
 subprocess.run(['docker','network','rm',network],capture_output=True)
 print('Disposable metadata test services and database volume removed.',flush=True)
