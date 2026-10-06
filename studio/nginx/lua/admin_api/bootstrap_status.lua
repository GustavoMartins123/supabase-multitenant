local cjson = require("cjson.safe")
local user_store = require("admin_api.authelia_user_store")
local authorization = require("security.bootstrap_authorization")

if ngx.var.request_method ~= "GET" then return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED) end
local result, err = user_store.with_lock(function()
    local data, _, load_err = user_store.load()
    if not data then return {error=load_err} end
    return {needs_admin=not authorization.closed(data.users)}
end)
ngx.header.content_type = "application/json"
ngx.header["Cache-Control"] = "no-store"
if not result or result.error then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.say(cjson.encode({error="Installation state unavailable"}))
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
ngx.say(cjson.encode(result))
