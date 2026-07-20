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

if method == "POST" and post_target then
    -- Rotas administrativas do Studio não coincidem com os paths do GoTrue.
    ngx.req.set_uri(post_target, false)
elseif method == "DELETE" and user_id then
    ngx.req.set_uri("auth/v1/admin/users/" .. user_id, false)
elseif method == "PATCH" and user_id then
    ngx.req.set_uri("auth/v1/admin/users/" .. user_id, false)
    ngx.req.set_method(ngx.HTTP_PUT)
else
    ngx.status = ngx.HTTP_NOT_IMPLEMENTED
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"unsupported_auth_operation"}')
    return ngx.exit(ngx.HTTP_NOT_IMPLEMENTED)
end
