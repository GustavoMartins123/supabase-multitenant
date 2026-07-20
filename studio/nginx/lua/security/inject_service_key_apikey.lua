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
ngx.req.set_header("apikey", key)
