local cjson = require "cjson.safe"
local slug  = ngx.var.slug

ngx.header["Access-Control-Allow-Origin"] = "*"
ngx.header["Access-Control-Allow-Methods"] = "GET, OPTIONS"
ngx.header["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

if not slug or slug == "" then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Slug inválido, retornando 400")
    return ngx.exit(400)
end

local include_members = ngx.var.arg_include_members == "true"
local mode = ngx.var.arg_mode or "owner"  -- "admin" ou "owner"
ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Request for project: ", slug, " include_members: ", tostring(include_members), " mode: ", mode)

local remote_email = ngx.req.get_headers()["Remote-Email"]
local remote_groups = ngx.req.get_headers()["Remote-Groups"]

local res = ngx.location.capture("/_internal_api/projects/" .. slug .. "/members", {
    method = ngx.HTTP_GET,
    headers = {
        ["Remote-Email"] = remote_email,
        ["Remote-Groups"] = remote_groups
    }
})

if res.status ~= 200 then
    ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] Erro no fetch de membros, status ", res.status)
    return ngx.exit(res.status)
end

local current = cjson.decode(res.body) or {}
local cache = ngx.shared.users_cache

if include_members then
    local admin_ids = {}
    local member_ids = {}
    
    for _, m in ipairs(current) do
        if m.role == "admin" then
            admin_ids[m.user_id] = true
            ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Found admin: ", m.user_id)
        else
            member_ids[m.user_id] = true
            ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Found member: ", m.user_id)
        end
    end
    
    local available = {}
    local keys, err = cache:get_keys(0)
    if not keys then
        ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] cache:get_keys error: ", err)
        return ngx.exit(500)
    end
    
    if mode == "admin" then
        ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Modo ADMIN: retornando todos os usuários ativos exceto admins")
        
        for _, h in ipairs(keys) do
            if h ~= "__mtime" and not admin_ids[h] then
                local ud_json = cache:get(h)
                if ud_json then
                    local ud = cjson.decode(ud_json)
                    if ud.is_active then
                        ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Adding user: ", ud.username, " (", h, ")")
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
        
        ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Returning ", #available, " users (excluding ", table.getn(admin_ids), " admins)")
    else
        ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Modo OWNER: priorizando membros atuais")
        
        local has_non_admin_members = false
        for _ in pairs(member_ids) do
            has_non_admin_members = true
            break
        end
        
        if has_non_admin_members then
            ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Retornando ", table.getn(member_ids), " membros não-admins")
            for _, h in ipairs(keys) do
                if member_ids[h] then
                    local ud_json = cache:get(h)
                    if ud_json then
                        local ud = cjson.decode(ud_json)
                        if ud.is_active then
                            table.insert(available, { 
                                user_id = h, 
                                display_name = ud.display_name,
                                username = ud.username,
                                is_active = true,
                                status = "member"
                            })
                        end
                    end
                end
            end
        else
            ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Sem membros não-admins, retornando usuários disponíveis")
            local all_project_users = {}
            for uid in pairs(admin_ids) do
                all_project_users[uid] = true
            end
            for uid in pairs(member_ids) do
                all_project_users[uid] = true
            end
            
            for _, h in ipairs(keys) do
                if h ~= "__mtime" and not all_project_users[h] then
                    local ud_json = cache:get(h)
                    if ud_json then
                        local ud = cjson.decode(ud_json)
                        if ud.is_active then
                            table.insert(available, { 
                                user_id = h, 
                                display_name = ud.display_name,
                                username = ud.username,
                                is_active = true,
                                status = "available"
                            })
                        end
                    end
                end
            end
        end
    end
    
    local json_response = cjson.encode(available)
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Returning ", #available, " users for transfer")
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] JSON response: ", json_response)
    ngx.header.content_type = "application/json"
    ngx.header.content_length = #json_response
    ngx.say(json_response)
    ngx.eof()
else
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Modo adicionar: excluindo membros atuais")
    local used = {}
    for _, m in ipairs(current) do
        if m.user_id then
            used[m.user_id] = true
            ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Excluding current member: ", m.user_id)
        end
    end

    local keys, err = cache:get_keys(0)
    if not keys then
        ngx.log(ngx.ERR, "[AVAILABLE][CONTENT] cache:get_keys error: ", err)
        return ngx.exit(500)
    end
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Cache keys count: ", #keys)
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Current members count: ", #current)

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
                else
                    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Skipping inactive user: ", ud.username, " (", h, ")")
                end
            end
        end
    end

    local json_response = cjson.encode(available)
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] Returning ", #available, " non-member users")
    ngx.log(ngx.INFO, "[AVAILABLE][CONTENT] JSON response: ", json_response)
    ngx.header.content_type = "application/json"
    ngx.header.content_length = #json_response
    ngx.say(json_response)
    ngx.eof()
end
