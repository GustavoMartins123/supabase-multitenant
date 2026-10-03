local context = require("security.project_access").enforce_admin()
if type(context) ~= "table" then
    return
end
require("security.storage_upload_limit").enforce(context)

local key = require("security.studio_administrative_key").load(context)
if not key or key == "" then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"project_service_unavailable"}')
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
ngx.req.set_header("Authorization", "Bearer " .. key)
ngx.req.set_header("apikey", key)
ngx.var.storage_upstream_uri = require("utils.proxy_uri").escape_path(ngx.var.uri)
