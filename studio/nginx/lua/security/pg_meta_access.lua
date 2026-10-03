local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Not authenticated")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local user_context_headers = require("project_context.user_context_headers")
user_context_headers.apply(email, ngx.var.authelia_groups or "")

local context = require("security.project_access").enforce_admin()
if type(context) ~= "table" then
    return
end

local get_service_key = require("security.get_service_key")
local key = get_service_key(context.ref)
if not key or key == "" then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"project_service_unavailable"}')
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
ngx.req.set_header("apikey", key)

local rewritten, rewrite_err = require("proxy_rewrites.pg_meta").rewrite(context)
if not rewritten then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say(require("cjson.safe").encode({ error = "invalid_pg_meta_request", message = rewrite_err }))
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

require("security.projects_api_signer").enforce()
