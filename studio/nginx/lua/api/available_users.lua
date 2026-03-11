local cjson = require "cjson.safe"
local slug  = ngx.var.slug

if not slug or slug == "" then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Slug inválido, retornando 400")
    return ngx.exit(400)
end

local res = ngx.location.capture("/_internal_api/projects/" .. slug .. "/members")

if res.status ~= 200 then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Erro no fetch de membros, status ", res.status)
    return ngx.exit(res.status)
end

local current = cjson.decode(res.body) or {}
local used = {}
for _, m in ipairs(current) do
    if m.user_id then
        used[m.user_id] = true
    end
end

local cache = ngx.shared.users_cache
local keys, err = cache:get_keys(0)
if not keys then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] cache:get_keys error: ", err)
    return ngx.exit(500)
end
ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Cache keys count: ", #keys)

local available = {}
for _, h in ipairs(keys) do
    if h ~= "__mtime" and not used[h] then
        local ud_json = cache:get(h)
        if ud_json then
            local ud = cjson.decode(ud_json)
            if ud.is_active then
                ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Adding available user: ", h)
                table.insert(available, { 
                    user_id = h, 
                    display_name = ud.display_name,
                    username = ud.username,
                    status = "active"
                })
            end
        end
    end
end

local json_response = cjson.encode(available)
ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] JSON final: ", json_response)
ngx.header.content_type = "application/json"
ngx.say(json_response)
