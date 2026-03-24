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
        
        local function watch_yaml_dir(premature)
        if premature then return end
        local pipe = require("ngx.pipe")
        
        local watch_dir = "/config/"
        local target_file = "users_database.yml"
        
        local proc, err = pipe.spawn({"inotifywait", "-q", "-m", "-e", "close_write,moved_to", watch_dir})
        
        if not proc then
            ngx.log(ngx.ERR, "[INOTIFY-PIPE] Falha ao iniciar inotifywait: ", err)
            return
        end

        ngx.log(ngx.INFO, "[INOTIFY-PIPE] Monitoramento iniciado no diretório: ", watch_dir)

        local function read_events()
            while true do
                local line, err = proc:stdout_read_line()
                
                if line then
                    if line:match(target_file) then
                        ngx.log(ngx.INFO, "[INOTIFY-PIPE] Arquivo modificado: ", line)
                        ngx.sleep(0.1)
                        
                        local ok, lerr = pcall(load_users)
                        if not ok then
                            ngx.log(ngx.ERR, "[INOTIFY-PIPE] Erro ao recarregar usuários: ", lerr)
                        end
                    end
                elseif err == "closed" then
                    ngx.log(ngx.INFO, "[INOTIFY-PIPE] Processo inotifywait finalizado.")
                    break
                elseif err ~= "timeout" and err ~= nil then
                    ngx.log(ngx.ERR, "[INOTIFY-PIPE] Erro na leitura do pipe: ", err)
                    break
                end
            end
        end

        ngx.thread.spawn(read_events)
    end
    if ngx.worker.id() == 0 then
        ngx.timer.at(0, watch_yaml_dir)
    end
