#!/bin/sh
set -eu
mkdir -p /config
openssl req -x509 -newkey rsa:2048 -nodes -keyout /config/test.key -out /config/test.crt -days 2 -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' >/dev/null 2>&1
openssl req -x509 -newkey rsa:2048 -nodes -keyout /config/untrusted.key -out /config/untrusted.crt -days 2 -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' >/dev/null 2>&1
# Synthetic service account with a real throwaway RSA key. No production secrets.
resty -e 'local c=require("cjson.safe");local f=assert(io.open("/config/test.key"));local k=f:read("*a");f:close();local o=assert(io.open("/config/firebase.json","w"));o:write(c.encode({client_email="push-test@example.test",project_id="shared-test",private_key=k}));o:close()'
resty -I /workspace/studio/nginx/lua --shdict 'push_oauth_tokens 1m' --shdict 'push_locks 1m' --shdict 'test_stats 1m' /workspace/tests/push/openresty/test_oauth.lua
openresty -t -c /workspace/tests/push/openresty/nginx.conf
exec openresty -c /workspace/tests/push/openresty/nginx.conf -g 'daemon off;'
