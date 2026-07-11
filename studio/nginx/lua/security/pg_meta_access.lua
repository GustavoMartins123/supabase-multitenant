local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Not authenticated")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local user_context_headers = require("project_context.user_context_headers")
user_context_headers.apply(email, ngx.var.authelia_groups or "")

local ref = ngx.var.project_ref
if not ref or ref == "default" then
    return
end

local get_service_key = require("security.get_service_key")
local key = get_service_key(ref)
if key and key ~= "" then
    ngx.req.set_header("apikey", key)
end
