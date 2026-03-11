        local lyaml = require "lyaml"
        local resty_sha2 = require "resty.sha256"
        local str = require "resty.string"
        local lfs = require "lfs"
        local cache = ngx.shared.users_cache
        local yaml = "/config/users_database.yml"
        
        local function load_users()
            local f = assert(io.open(yaml))
            local t = lyaml.load(f:read("*a")); f:close()
            cache:flush_all()
            ngx.log(ngx.INFO, "Carregando usuários do arquivo YAML…")
            
            for uname, attr in pairs(t.users or {}) do
                local groups = attr.groups or {}
                local is_active = false
                local is_admin = false
                
                -- Verificar se é ativo e se é admin
                for _, group in ipairs(groups) do
                    if group == "active" then
                        is_active = true
                    elseif group == "admin" then
                        is_admin = true
                    end
                end
                
                local email = (attr.email or ""):lower():gsub("%s+", "")
                local display_name = attr.displayname or uname
                local hasher = resty_sha2:new()
                hasher:update(email)
                local digest = hasher:final()
                local hash = str.to_hex(digest)
                local cjson = require "cjson.safe"
                
                if is_active then
                    cache:set(hash, cjson.encode({
                        email = email,
                        display_name = display_name,
                        username = uname,
                        is_active = true,
                        is_admin = is_admin
                    }))
                    ngx.log(ngx.INFO, "Usuário ATIVO carregado: " .. uname .. " (" .. email .. ") - Admin: " .. tostring(is_admin))
                else
                    cache:set(hash, cjson.encode({
                        email = email,
                        display_name = display_name .. " (INATIVO)",
                        username = uname,
                        is_active = false,
                        is_admin = is_admin 
                    }))
                    ngx.log(ngx.INFO, "Usuário INATIVO mantido no cache: " .. uname .. " (" .. email .. ") - Admin: " .. tostring(is_admin))
                end
                
                ngx.log(ngx.INFO, "[CACHE] set() – user=", uname,
                    " email=", email,
                    " hash=", hash,
                    " active=", is_active,
                    " admin=", is_admin)
            end
            
            cache:set("__mtime", lfs.attributes(yaml, "modification"))
            ngx.log(ngx.INFO, "[CACHE] Cache atualizado em mtime=", cache:get("__mtime"))
        end
        
        load_users()
        
        local keys, err = cache:get_keys(0)
        if keys then
            ngx.log(ngx.INFO, "[CACHE] total keys loaded: ", #keys)
        else
            ngx.log(ngx.INFO, "[CACHE] get_keys error: ", err)
        end
        
        ngx.timer.every(10, function()
            local m = lfs.attributes(yaml, "modification")
            if cache:get("__mtime") ~= m then
                ngx.log(ngx.INFO, "[CACHE] Detected YAML change (old=", cache:get("__mtime"),
                    " new=", m, "), recarregando…")
                load_users()
            end
        end)
