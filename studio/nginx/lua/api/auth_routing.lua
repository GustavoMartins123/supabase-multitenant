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
local post_routes = {
    ["/api/platform/auth/default/invite"] = "auth/v1/invite",
    ["/api/platform/auth/default/recover"] = "auth/v1/recover",
    ["/api/platform/auth/default/magiclink"] = "auth/v1/magiclink",
}

local post_target = post_routes[uri]

if method == "POST" and post_target then
    ngx.req.set_uri(post_target, false)
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
