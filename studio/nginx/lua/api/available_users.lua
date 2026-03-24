local cjson = require "cjson.safe"
local slug  = ngx.var.slug

if not slug or slug == "" then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Slug inválido, retornando 400")
    return ngx.exit(400)
end

local include_members = ngx.var.arg_include_members == "true"

local res = ngx.location.capture("/_internal_api/projects/" .. slug .. "/members")

if res.status ~= 200 then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Erro no fetch de membros, status ", res.status)
    return ngx.exit(res.status)
end

local current = cjson.decode(res.body) or {}
local cache = ngx.shared.users_cache

if include_members then
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Modo transferência: incluindo membros atuais")
    local available = {}
    
    for _, m in ipairs(current) do
        if m.user_id then
            local ud_json = cache:get(m.user_id)
            if ud_json then
                local ud = cjson.decode(ud_json)
                if ud.is_active then
                    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Adding member: ", ud.username, " (", m.user_id, ")")
                    table.insert(available, { 
                        user_id = m.user_id, 
                        display_name = ud.display_name,
                        username = ud.username,
                        is_active = true,
                        status = "active"
                    })
                else
                    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Skipping inactive member: ", ud.username)
                end
            else
                ngx.log(ngx.WARN, "[AVAILABLE][CONTENT] Member not found in cache: ", m.user_id)
            end
        end
    end
    
    if #available == 0 then
        ngx.log(ngx.WARN, "[AVAILABLE][CONTENT] Nenhum membro ativo encontrado, usando fallback para todos os usuários")
        
        local keys, err = cache:get_keys(0)
        if not keys then
            ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] cache:get_keys error: ", err)
            return ngx.exit(500)
        end
        
        for _, h in ipairs(keys) do
            if h ~= "__mtime" then
                local ud_json = cache:get(h)
                if ud_json then
                    local ud = cjson.decode(ud_json)
                    if ud.is_active then
                        ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Adding fallback user: ", ud.username, " (", h, ")")
                        table.insert(available, { 
                            user_id = h, 
                            display_name = ud.display_name,
                            username = ud.username,
                            is_active = true,
                            status = "active"
                        })
                    end
                end
            end
        end
        
        ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Fallback: returning ", #available, " active users")
    end
    
    local json_response = cjson.encode(available)
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Returning ", #available, " users for transfer")
    ngx.header.content_type = "application/json"
    ngx.say(json_response)
else
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Modo adicionar: excluindo membros atuais")
    local used = {}
    for _, m in ipairs(current) do
        if m.user_id then
            used[m.user_id] = true
        end
    end

    local keys, err = cache:get_keys(0)
    if not keys then
        ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] cache:get_keys error: ", err)
        return ngx.exit(500)
    end
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Cache keys count: ", #keys)

    local available = {}
    for _, h in ipairs(keys) do
        if h ~= "__mtime" and not used[h] then
            local ud_json = cache:get(h)
            if ud_json then
                local ud = cjson.decode(ud_json)
                if ud.is_active then
                    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Adding available user: ", ud.username, " (", h, ")")
                    table.insert(available, { 
                        user_id = h, 
                        display_name = ud.display_name,
                        username = ud.username,
                        is_active = true,
                        status = "active"
                    })
                end
            end
        end
    end

    local json_response = cjson.encode(available)
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Returning ", #available, " non-member users")
    ngx.header.content_type = "application/json"
    ngx.say(json_response)
end
