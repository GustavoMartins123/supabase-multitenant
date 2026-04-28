local cjson  = require "cjson.safe"
local cache  = ngx.shared.users_cache
local uri    = "/_internal_api/projects/" .. ngx.var.slug .. "/members"

local res = ngx.location.capture(uri, { method = ngx.HTTP_GET })
if res.status ~= 200 then return ngx.exit(res.status) end
local members = cjson.decode(res.body) or {}

-- Enriquece com dados do cache e marca status
for _, m in ipairs(members) do
    local cache_key = m.user_hash or m.user_id
    local ud_json = cache:get(cache_key)
    if ud_json then
        local ud = cjson.decode(ud_json)
        m.display_name = ud.display_name
        m.username = ud.username
        m.is_active = ud.is_active
        m.status = ud.is_active and "active" or "inactive"
    else
        -- Usuário não encontrado no cache (removido completamente)
        m.display_name = "Usuário Removido"
        m.username = "unknown"
        m.is_active = false
        m.status = "removed"
    end
end

ngx.header.content_type = "application/json"
ngx.say(cjson.encode(members))
