require("security.storage_upload_limit").enforce()

local project_ref = ngx.var.project_ref
if not project_ref or project_ref == "default" then
    return
end

local get_service_key = require("security.get_service_key")
local key = get_service_key(project_ref)
if key and key ~= "" then
    ngx.req.set_header("Authorization", "Bearer " .. key)
    ngx.req.set_header("apikey", key)
    ngx.ctx.service_key = key
end

-- Algumas rotas de plataforma precisam combinar mais de uma operacao real do
-- Storage API. O Studio oficial, por exemplo, lista os indexes e depois chama
-- GetIndex para obter dimension e distanceMetric de cada item.
require("proxy_rewrites.storage_vector_platform").handle()
