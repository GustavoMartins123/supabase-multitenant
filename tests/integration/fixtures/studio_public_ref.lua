local cjson = require("cjson.safe")
local http = require("resty.http")
local root = "/workspace/studio/nginx/lua"
package.path = root .. "/?.lua;" .. root .. "/?/init.lua;" .. package.path
for _, name in ipairs({
    "cache/invalidate_service_key", "project_context/project_ref_resolver",
    "project_context/studio_context", "proxy_rewrites/pg_meta", "security/get_service_key",
    "security/internal_hmac", "security/pg_meta_access", "security/projects_api_signer",
    "security/step_up_authenticate",
}) do
    assert(loadfile(root .. "/" .. name .. ".lua"))
end

local ref = "abcdefghijklmnopqrst"
local other = "bcdefghijklmnopqrstu"
local resolver = require("project_context.project_ref_resolver")
assert(resolver.valid_ref(ref))
for _, invalid in ipairs({ "technical_project", "ABCDefghijklmnopqrst", ref .. "a", ref:sub(2),
    "11111111-1111-4111-8111-111111111111", "abcdefghijklmno12345", " " .. ref }) do
    assert(not resolver.valid_ref(invalid), invalid)
    local resolved, has_path, err = resolver.ref_from_path("/project/" .. invalid .. "/editor")
    assert(not resolved and has_path and err == "invalid_path_ref", invalid)
end

local signer = require("security.projects_api_signer")
local request_vars = ngx.var
ngx.var = {}
ngx.ctx.studio_request_project_ref = ref
local target = signer.target_for_request("/api/platform/projects/" .. ref .. "/content/item/11111111-1111-4111-8111-111111111111")
assert(target:find("/api/projects/" .. ref .. "/content/item/", 1, true) == 1)
assert(not signer.target_for_request("/api/platform/projects/" .. other .. "/content"))
ngx.ctx.studio_request_project_ref = nil
ngx.var = request_vars
print("PASS: content requests retain their canonical public reference and reject mismatched context")

assert(os.execute("mkdir -p /tmp/studio-ref/body /tmp/studio-ref/logs") == true)
local conf = [[
worker_processes 1;
pid /tmp/studio-ref/nginx.pid;
error_log /tmp/studio-ref/error.log warn;
env SERVER_DOMAIN;
env STUDIO_GATEWAY_HMAC_SECRET;
env PROJECTS_API_HMAC_SECRET;
events { worker_connections 64; }
http {
    access_log off;
    client_body_temp_path /tmp/studio-ref/body;
    proxy_temp_path /tmp/studio-ref/proxy;
    lua_package_path "/workspace/studio/nginx/lua/?.lua;/workspace/studio/nginx/lua/?/init.lua;;";
    lua_shared_dict internal_hmac_nonces 1m;
    lua_shared_dict service_keys 1m;
    lua_shared_dict service_key_metrics 1m;
    init_by_lua_block {
        package.loaded["project_context.user_context_headers"] = {
            apply = function()
                ngx.var.auth_user_id = "11111111-1111-4111-8111-111111111111"
                ngx.var.auth_user_token = "fixture-user-token"
            end,
        }
        package.loaded["security.get_service_key"] = function(ref)
            assert(ref == "abcdefghijklmnopqrst")
            if ngx.var.http_x_test_key_failure then return nil end
            return "fixture-service-key"
        end
        package.loaded["resty.http"] = {
            new = function()
                return {
                    set_timeout = function() end,
                    request_uri = function(_, url, options)
                        assert(options.ssl_verify == true)
                        assert(options.headers["X-User-Token"] == "fixture-user-token")
                        assert(options.headers["X-Internal-Signature"])
                        if url ~= "http://127.0.0.1:19842/api/projects/internal/studio-context/abcdefghijklmnopqrst?access=admin"
                            or ngx.var.http_x_test_role ~= "admin" then
                            return { status = 403, body = '{}' }
                        end
                        return {
                            status = 200,
                            body = require("cjson.safe").encode({
                                ref = "abcdefghijklmnopqrst",
                                technical_name = ngx.var.http_x_test_technical_name or "technical_project",
                                project_uuid = "11111111-1111-4111-8111-111111111111",
                                tenant_uuid = "22222222-2222-4222-8222-222222222222",
                                anon_key = "fixture-anon-key",
                                enc_admin_key = "fixture-encrypted-admin-key",
                            }),
                        }
                    end,
                }
            end,
        }
    }
    server {
        listen 127.0.0.1:19842;
        set $authelia_email $http_x_test_user;
        set $authelia_groups "active";
        set $auth_user_id "";
        set $auth_user_token "";
        set $project_ref "";
        set $server_path "";
        location ~ "^/api/platform/pg-meta/([a-z]{20})(/.*)?$" {
            set $resource $2;
            client_body_buffer_size 1k;
            access_by_lua_file /workspace/studio/nginx/lua/security/pg_meta_access.lua;
            proxy_pass http://127.0.0.1:19843/api/projects/$project_ref/meta$resource$is_args$args;
        }
        location / { return 404; }
        location ~ "^/internal/cache/service-key/(?<cache_ref>[a-z]{20})$" {
            client_body_buffer_size 1k;
            content_by_lua_file /workspace/studio/nginx/lua/cache/invalidate_service_key.lua;
        }
    }
    server {
        listen 127.0.0.1:19843;
        location / {
            content_by_lua_block {
                local hmac = require("security.internal_hmac")
                local valid, status, err = hmac.verify_current_request(
                    os.getenv("STUDIO_GATEWAY_HMAC_SECRET"), "studio-nginx")
                if not valid then ngx.status = status; ngx.say(err); return end
                local cjson = require("cjson.safe")
                ngx.say(cjson.encode({
                    target = ngx.var.request_uri,
                    body = hmac.read_current_body(),
                    project_ref = ngx.var.http_x_project_ref,
                    tab_header = ngx.var.http_x_studio_project_ref,
                    apikey = ngx.var.http_apikey,
                }))
            }
        }
    }
}
]]
local file = assert(io.open("/tmp/studio-ref/nginx.conf", "w"))
assert(file:write(conf))
file:close()
assert(os.execute("nginx -p /tmp/studio-ref/ -c /tmp/studio-ref/nginx.conf") == true)

local count = 0
local function request(resource, body, overrides, expected)
    local headers = { ["X-Test-User"] = "admin@example.test", ["X-Test-Role"] = "admin" }
    for name, value in pairs(overrides or {}) do headers[name] = value end
    if body then headers["Content-Type"] = "application/json" end
    local response = assert(http.new():request_uri("http://127.0.0.1:19842" .. resource, {
        method = body and "POST" or "GET", body = body, headers = headers,
    }))
    assert(response.status == (expected or 200), tostring(response.status) .. ": " .. response.body)
    count = count + 1
    if response.status == 200 then
        local echo = assert(cjson.decode(response.body))
        assert(echo.apikey == "fixture-service-key")
        assert(echo.project_ref == ref)
        assert(echo.tab_header == nil)
        return echo
    end
end

local ok, err = xpcall(function()
    local base = "/api/platform/pg-meta/" .. ref
    local wrapper = "CREATE FOREIGN DATA WRAPPER s3_vectors HANDLER s3_vectors_fdw_handler "
        .. "VALIDATOR s3_vectors_fdw_validator OPTIONS (endpoint_url 'https://untrusted.example/vector')"
    local echo = request(base .. "/query", cjson.encode({ query = wrapper }))
    local query = assert(cjson.decode(echo.body)).query
    assert(query:find("http://supabase-nginx-technical_project:8081/vector", 1, true))
    assert(not query:find(ref, 1, true) and not query:find("untrusted.example", 1, true))
    assert(echo.target == "/api/projects/" .. ref .. "/meta/query")

    echo = request(base .. "/columns?id=42&mode=full", '{"tableId":123,"isNullable":false}')
    assert(echo.target == "/api/projects/" .. ref .. "/meta/columns/42?mode=full")
    local converted = assert(cjson.decode(echo.body))
    assert(converted.table_id == 123 and converted.is_nullable == false and converted.tableId == nil)
    echo = request(base .. "/policies?included_schemas=&excluded_schemas=")
    assert(echo.target == "/api/projects/" .. ref .. "/meta/policies")

    echo = request(base .. "/query", cjson.encode({ query = "select '" .. string.rep("x", 8192) .. "'" }))
    assert(#echo.body > 8192)
    request(base .. "/query", "{broken", nil, 400)
    request(base .. "/query", "[]", nil, 400)
    request(base .. "/query", cjson.encode({ query = wrapper:gsub("endpoint_url", "removed_option") }), nil, 400)
    request(base .. "/query", cjson.encode({ query = wrapper .. " endpoint_url 'http://extra'" }), nil, 400)
    request(base .. "/columns?id=1&id=2", nil, nil, 400)
    request(base .. "/columns?id=", nil, nil, 400)
    request(base .. "/columns?" .. string.rep("x=1&", 101), nil, nil, 400)
    request(base .. "/query", nil, { ["X-Studio-Project-Ref"] = other }, 409)
    request(base .. "/query", nil, { ["X-Studio-Project-Ref"] = "technical_project" }, 400)
    request(base .. "/query", "{broken", { ["X-Test-User"] = "" }, 401)
    request(base .. "/query", "{broken", { ["X-Test-Role"] = "member" }, 404)
    request(base .. "/query", nil, { ["X-Test-Key-Failure"] = "1" }, 503)
    request(base .. "/query", nil, { ["X-Test-Technical-Name"] = "../escape" }, 503)
    request("/api/platform/pg-meta/technical_project/query", nil, nil, 404)
    request("/api/platform/pg-meta/11111111-1111-4111-8111-111111111111/query", nil, nil, 404)
    request("/api/platform/pg-meta/" .. ref .. "a/query", nil, nil, 404)
    request("/api/platform/pg-meta/" .. other .. "/query", nil, nil, 404)

    local hmac = require("security.internal_hmac")
    local function invalidate(target_ref, body, expected, signed)
        local path = "/internal/cache/service-key/" .. target_ref
        local headers = { ["Content-Type"] = "application/json" }
        if signed ~= false then
            headers = assert(hmac.sign_headers(os.getenv("PROJECTS_API_HMAC_SECRET"), "projects-api", "POST", path, body))
        end
        local response = assert(http.new():request_uri("http://127.0.0.1:19842" .. path, {
            method = "POST", body = body, headers = headers,
        }))
        assert(response.status == expected, tostring(response.status) .. ": " .. response.body)
        count = count + 1
        return cjson.decode(response.body)
    end
    local invalidation = invalidate(ref, '{"project_key_version":7}', 200)
    assert(invalidation.project_ref == ref and invalidation.project_key_version == 7)
    invalidation = invalidate(ref, '{"project_key_version":6}', 200)
    assert(invalidation.project_key_version == 7)
    invalidation = invalidate(other, '{"project_key_version":2}', 200)
    assert(invalidation.project_key_version == 2 and invalidation.project_ref == other)
    invalidate(ref, '{"project_key_version":8,"padding":"' .. string.rep("x", 8192) .. '"}', 200)
    invalidate(ref, '{"project_key_version":8}', 401, false)
    invalidate(ref, "{broken", 400)
    invalidate(ref, "[]", 400)
    invalidate(ref, '{"project_key_version":1.5}', 400)
    invalidate(ref, '{"project_key_version":0}', 400)
    invalidate("technical_project", '{"project_key_version":8}', 404)
end, debug.traceback)
assert(os.execute("nginx -p /tmp/studio-ref/ -c /tmp/studio-ref/nginx.conf -s quit") == true)
if not ok then
    local log = assert(io.open("/tmp/studio-ref/error.log", "r"))
    io.stderr:write(log:read("*a")); log:close()
    error(err)
end
print("Studio public reference: " .. count .. " HTTP cases passed; final target and body HMAC verified")
