local cjson = require("cjson.safe")
local http = require("resty.http")
local root = "/workspace/studio/nginx/lua"
package.path = root .. "/?.lua;" .. root .. "/?/init.lua;" .. package.path
assert(os.execute("mkdir -p /tmp/content-gateway/body /tmp/content-gateway/logs"))
local config = [[
worker_processes 1;
pid /tmp/content-gateway/nginx.pid;
error_log /tmp/content-gateway/error.log warn;
env STUDIO_GATEWAY_HMAC_SECRET;
env SERVER_DOMAIN;
events { worker_connections 64; }
http {
    access_log off;
    client_body_temp_path /tmp/content-gateway/body;
    lua_package_path "/workspace/studio/nginx/lua/?.lua;;";
    lua_shared_dict internal_hmac_nonces 1m;
    init_by_lua_block {
        package.loaded["project_context.user_context_headers"] = {
            apply = function()
                ngx.var.auth_user_id = "11111111-1111-4111-8111-111111111111"
                ngx.var.auth_user_token = "fixture-authenticated-user"
                ngx.req.set_header("X-User-Token", ngx.var.auth_user_token)
            end,
        }
        package.loaded["project_context.studio_context"] = {
            load = function(ref)
                if ref ~= "abcdefghijklmnopqrst" then return nil, "Project not found", 404 end
                return {ref=ref,project_uuid="22222222-2222-4222-8222-222222222222"}
            end,
        }
    }
    server {
        listen 127.0.0.1:19852;
        set $authelia_email $http_x_test_user;
        set $authelia_groups "active";
        set $auth_user_id "";
        set $auth_user_token "";
        set $project_ref "";
        set $server_path "";
        location ~ "^/api/platform/projects/(?<content_ref>[a-z]{20})/content(?<content_resource>(?:/.*)?)$" {
            client_body_buffer_size 1k;
            access_by_lua_file /workspace/studio/nginx/lua/security/studio_content_access.lua;
            proxy_set_header X-User-Token $auth_user_token;
            proxy_pass http://127.0.0.1:19853/api/projects/$content_ref/content$content_resource$is_args$args;
        }
        location / { return 404; }
    }
    server {
        listen 127.0.0.1:19853;
        location / {
            content_by_lua_block {
                local hmac = require("security.internal_hmac")
                local valid,status = hmac.verify_current_request(os.getenv("STUDIO_GATEWAY_HMAC_SECRET"),"studio-nginx")
                if not valid then ngx.status=status; return end
                ngx.say(require("cjson.safe").encode({target=ngx.var.request_uri,body=hmac.read_current_body(),user=ngx.var.http_x_user_token}))
            }
        }
    }
}
]]
local file = assert(io.open("/tmp/content-gateway/nginx.conf", "w"))
file:write(config); file:close()
assert(os.execute("nginx -p /tmp/content-gateway/ -c /tmp/content-gateway/nginx.conf"))
local ref = "abcdefghijklmnopqrst"
local base = "/api/platform/projects/" .. ref .. "/content"
local checks = 0
local function request(method, path, body, status, headers)
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    local result = assert(http.new():request_uri("http://127.0.0.1:19852" .. path, {method=method,body=body,headers=headers}))
    assert(result.status == status, "Unexpected content gateway status: " .. tostring(result.status))
    checks = checks + 1
    if status == 200 then
        local echo = assert(cjson.decode(result.body))
        assert(echo.target == path:gsub("/api/platform/projects/", "/api/projects/", 1))
        assert(echo.body == (body or ""), "Gateway must not transform SQL content or IDs")
        assert(echo.user == "fixture-authenticated-user")
    end
end
local ok, err = xpcall(function()
    local headers = { ["X-Test-User"]="test@example.test",["X-Studio-Project-Ref"]=ref }
    request("GET", base .. "?type=sql&limit=100", nil, 200, headers)
    request("GET", base .. "/count?type=sql", nil, 200, headers)
    request("GET", base .. "/item/33333333-3333-4333-8333-333333333333", nil, 200, headers)
    local body = cjson.encode({id="33333333-3333-4333-8333-333333333333",type="sql",name="Untitled",visibility="user",
        content={content_id="33333333-3333-4333-8333-333333333333",schema_version="1.0",sql=string.rep(" ",8192)}})
    request("PUT", base, body, 200, headers)
    request("DELETE", base .. "?ids=33333333-3333-4333-8333-333333333333", nil, 200, headers)
    request("POST", base .. "/folders", '{"name":"Queries"}', 200, headers)
    request("PATCH", base .. "/folders/44444444-4444-4444-8444-444444444444", '{"name":"Renamed"}', 200, headers)
    request("GET", base, nil, 401)
    request("GET", base, nil, 409, {["X-Test-User"]="test@example.test",["X-Studio-Project-Ref"]="bcdefghijklmnopqrstu"})
    request("GET", "/api/platform/projects/bcdefghijklmnopqrstu/content", nil, 404, {["X-Test-User"]="test@example.test"})
    request("GET", "/api/platform/projects/technical_name/content", nil, 404, headers)
    request("PUT", base, body, 200, {["X-Test-User"]="test@example.test",["X-User-Token"]="forged-user-token",["X-Internal-Signature"]="forged"})
end, debug.traceback)
os.execute("nginx -p /tmp/content-gateway/ -c /tmp/content-gateway/nginx.conf -s stop")
if not ok then
    local errors = assert(io.open("/tmp/content-gateway/error.log", "r"))
    print(errors:read("*a")); errors:close()
end
assert(ok, err)
print("PASS: " .. checks .. " signed content gateway checks; IDs and body preserved")
