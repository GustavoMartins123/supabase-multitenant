local cjson = require "cjson.safe"
local slug = ngx.var.slug

if not slug or slug == "" then
    ngx.log(ngx.ERR, "[ALL-USERS] Slug inválido")
    return ngx.exit(400)
end

-- FONTE 1: Buscar membros atuais do projeto (API Python)
local members_res = ngx.location.capture("/_internal_api/projects/" .. slug .. "/members")
local current_members = {}
local member_lookup = {}
local admin_users = {} -- Track de usuários que já são admin

if members_res.status == 200 then
    current_members = cjson.decode(members_res.body) or {}
    for _, m in ipairs(current_members) do
        if m.user_id then
            member_lookup[m.user_id] = {
                role = m.role,
                is_member = true
            }
            
            -- Marcar usuários que já são admin
            if m.role == "admin" then
                admin_users[m.user_id] = true
            end
        end
    end
    ngx.log(ngx.ERR, "[ALL-USERS] Found ", #current_members, " current members")
else
    ngx.log(ngx.ERR, "[ALL-USERS] Failed to fetch members, status: ", members_res.status)
end

-- FONTE 2: Buscar todos os usuários do cache (Nginx)
local cache = ngx.shared.users_cache
local keys, err = cache:get_keys(0)
if not keys then
    ngx.log(ngx.ERR, "[ALL-USERS] cache:get_keys error: ", err)
    return ngx.exit(500)
end

ngx.log(ngx.ERR, "[ALL-USERS] Cache has ", #keys, " user keys")

-- COMBINAR: Criar lista de usuários disponíveis para transferência
local all_users = {}
local users_found = 0
local members_found = 0
local available_found = 0
local admins_excluded = 0

for _, user_hash in ipairs(keys) do
    if user_hash ~= "__mtime" then
        local user_json = cache:get(user_hash)
        if user_json then
            local user_data = cjson.decode(user_json)
            
            if user_data then
                users_found = users_found + 1
                
                -- LÓGICA DE FILTRAGEM:
                -- Incluir APENAS se:
                -- 1. NÃO é membro do projeto (disponível para entrar)
                -- 2. É membro mas NÃO é admin (pode virar admin)
                local is_current_admin = admin_users[user_hash] == true
                
                if not is_current_admin then
                    local user_info = {
                        user_id = user_hash,
                        display_name = user_data.display_name or "Unknown",
                        username = user_data.username or "unknown",
                        is_active = user_data.is_active or false,
                        status = "available"
                    }
                    
                    -- Se é membro atual (mas não admin), enriquecer com dados do projeto
                    if member_lookup[user_hash] then
                        user_info.status = "member"
                        user_info.project_role = member_lookup[user_hash].role
                        members_found = members_found + 1
                        ngx.log(ngx.ERR, "[ALL-USERS] Including non-admin member: ", user_data.display_name, " role: ", member_lookup[user_hash].role)
                    else
                        available_found = available_found + 1
                        ngx.log(ngx.ERR, "[ALL-USERS] Including available user: ", user_data.display_name)
                    end
                    
                    table.insert(all_users, user_info)
                end
            end
        end
    end
end

-- Verificar se existem membros no banco que não estão no cache
-- (excluindo admins)
local orphaned_members = {}
for _, member in ipairs(current_members) do
    local is_admin = (member.role == "admin")
    
    if not is_admin then -- Só processar não-admins
        local found_in_cache = false
        for _, user in ipairs(all_users) do
            if user.user_id == member.user_id then
                found_in_cache = true
                break
            end
        end
        
        if not found_in_cache then
            table.insert(orphaned_members, {
                user_id = member.user_id,
                display_name = "Unknown User",
                username = "unknown",
                is_active = false,
                status = "member",
                project_role = member.role,
                note = "User not found in cache"
            })
        end
    end
end

-- Adicionar membros órfãos à lista
for _, orphan in ipairs(orphaned_members) do
    table.insert(all_users, orphan)
end

-- Ordenar por status (membros primeiro) e depois por display_name
table.sort(all_users, function(a, b)
    if a.status ~= b.status then
        return a.status == "member"
    end
    return (a.display_name or "") < (b.display_name or "")
end)

-- Resposta estruturada
local response = {
    project_slug = slug,
    summary = {
        total_users = #all_users,
        current_members = members_found, -- Membros não-admin incluídos
        available_users = available_found, -- Usuários disponíveis
        orphaned_members = #orphaned_members,
        cache_keys = #keys - 1
    },
    users = all_users
}

ngx.log(ngx.ERR, "[ALL-USERS] Response summary: ", cjson.encode(response.summary))

ngx.header.content_type = "application/json"
ngx.say(cjson.encode(response))
