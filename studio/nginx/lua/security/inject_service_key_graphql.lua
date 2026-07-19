local project_ref = ngx.var.project_ref
local context = require("security.project_access").enforce(project_ref)
if type(context) ~= "table" then
    return
end

local get_service_key = require("security.get_service_key")
local key = get_service_key(project_ref)
if not key or key == "" then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"project_service_unavailable"}')
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

local headers = ngx.req.get_headers()
local authorization = headers["X-GraphQL-Authorization"]
    or headers["x-graphql-authorization"]
    or ("Bearer " .. context.anon_key)

ngx.req.set_header("apikey", key)
ngx.req.set_header("Authorization", authorization)
