local context = require("security.project_access").enforce()
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
ngx.req.set_header("Authorization", "Bearer " .. key)
ngx.req.set_header("apikey", key)

local method = ngx.var.request_method
local uri = ngx.var.uri
local relative_path = uri:match("^/api/platform/auth/[^/]+/(.+)$") or ""
local user_id = relative_path:match("^users/([^/]+)$")
local post_routes = {
    invite = "auth/v1/invite",
    recover = "auth/v1/recover",
    magiclink = "auth/v1/magiclink",
    otp = "auth/v1/otp",
    users = "auth/v1/admin/users",
}

local post_target = post_routes[relative_path]
local gotrue_path = nil

if method == "POST" and post_target then
    gotrue_path = post_target
elseif method == "GET" and relative_path == "users" then
    gotrue_path = "auth/v1/admin/users"
elseif method == "GET" and user_id then
    gotrue_path = "auth/v1/admin/users/" .. user_id
elseif method == "DELETE" and user_id then
    gotrue_path = "auth/v1/admin/users/" .. user_id
elseif method == "PATCH" and user_id then
    gotrue_path = "auth/v1/admin/users/" .. user_id
    ngx.req.set_method(ngx.HTTP_PUT)
end

if not gotrue_path then
    ngx.status = ngx.HTTP_NOT_IMPLEMENTED
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"unsupported_auth_operation"}')
    return ngx.exit(ngx.HTTP_NOT_IMPLEMENTED)
end

ngx.req.set_uri(gotrue_path, false)

local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local hmac_secret = os.getenv("STUDIO_GATEWAY_HMAC_SECRET")
if server_domain == "" or not hmac_secret or hmac_secret == "" then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"auth_admin_proxy_unconfigured"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local internal_hmac = require("security.internal_hmac")
local sign_target = "/api/projects/internal/auth-admin/"
    .. context.ref
    .. ngx.var.uri
    .. (ngx.var.is_args or "")
    .. (ngx.var.args or "")
local signed, sign_err =
    internal_hmac.apply_current_request(hmac_secret, "studio-nginx", sign_target)
if not signed then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"auth_admin_proxy_signing_failed"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

ngx.var.server_path = server_domain .. "/api/projects/internal/auth-admin/" .. context.ref
