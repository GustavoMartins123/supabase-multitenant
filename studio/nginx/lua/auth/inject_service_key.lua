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
