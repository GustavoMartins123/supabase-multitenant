local context = require("security.project_access").enforce_admin()
if type(context) ~= "table" then
    return
end
require("security.storage_upload_limit").enforce(context)
require("proxy_rewrites.storage_public_url").handle(context)

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
ngx.ctx.service_key = key

-- Algumas rotas de plataforma precisam combinar mais de uma operacao real do
-- Storage API. O Studio oficial, por exemplo, lista os indexes e depois chama
-- GetIndex para obter dimension e distanceMetric de cada item.
require("proxy_rewrites.storage_vector_platform").handle()
