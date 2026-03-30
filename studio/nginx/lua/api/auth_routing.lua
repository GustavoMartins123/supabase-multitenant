local ref = ngx.var.project_ref
if not ref or ref == "default" then
    return
end
local get = require "get_service_key"
local key = get(ref)
if key and key ~= "" then
    ngx.req.set_header("Authorization", "Bearer " .. key)
    ngx.req.set_header("apikey", key)
end

local proj = ngx.var.project_ref
local method = ngx.var.request_method
local uri = ngx.var.uri
local user_id = uri:match("^/api/platform/auth/default/users/(.+)$")
local is_invite = uri:match("^/api/platform/auth/default/invite$")

if method == "POST" and is_invite then
    ngx.req.set_uri("auth/v1/invite", false)
elseif method == "POST" and not user_id then
    ngx.req.set_uri("auth/v1/signup", false)
elseif method == "DELETE" and user_id then
    ngx.req.set_uri("auth/v1/admin/users/" .. user_id, false)
elseif method == "PATCH" and user_id then
    ngx.req.set_uri("auth/v1/admin/users/" .. user_id, false)
    ngx.req.set_method(ngx.HTTP_PUT)
else
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say("Requisição inválida para " .. method .. " em " .. uri)
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end
