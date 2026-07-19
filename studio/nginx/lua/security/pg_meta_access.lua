local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Not authenticated")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local user_context_headers = require("project_context.user_context_headers")
user_context_headers.apply(email, ngx.var.authelia_groups or "")

local ref = ngx.var.project_ref
local context = require("security.project_access").enforce(ref)
if type(context) ~= "table" then
    return
end

local get_service_key = require("security.get_service_key")
local key = get_service_key(ref)
if not key or key == "" then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"project_service_unavailable"}')
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
ngx.req.set_header("apikey", key)
