        local lyaml = require "lyaml"
        local lfs = require "lfs"
        local user_identity = require "user_identity"
        local authelia_identifiers = require "authelia_identifiers"
        local user_sync = require "user_sync"
        local cache = ngx.shared.users_cache
        local yaml = "/config/users_database.yml"

        local function queue_user_sync(users_for_sync)
            if ngx.worker.id() ~= 0 or not users_for_sync or #users_for_sync == 0 then
                return
            end

            local ok, timer_err = ngx.timer.at(0, function(premature, payloads)
                if premature then
                    return
                end

                local synced = 0
                for _, payload in ipairs(payloads) do
                    local sync_result, sync_err = user_sync.sync_user(payload)
                    if sync_err then
                        ngx.log(ngx.ERR, "[SYNC] Falha ao sincronizar usuario ", payload.username, ": ", sync_err)
                    else
                        local cache_key = payload.cache_key
                        local cached_json = cache:get(cache_key)
                        if cached_json and sync_result and sync_result.id then
                            local cjson = require "cjson.safe"
                            local cached_user = cjson.decode(cached_json)
                            if cached_user then
                                cached_user.user_uuid = sync_result.id
                                local encoded = cjson.encode(cached_user)
                                cache:set(cache_key, encoded)
                                cache:set(sync_result.id, encoded)
                                if cached_user.email and cached_user.email ~= "" then
                                    cache:set("email:" .. cached_user.email, sync_result.id)
                                end
                            end
                        end
                        synced = synced + 1
                    end
                end

                ngx.log(ngx.INFO, "[SYNC] Usuarios sincronizados com backend: ", synced, "/", #payloads)
            end, users_for_sync)

            if not ok then
                ngx.log(ngx.ERR, "[SYNC] Falha ao agendar sincronizacao de usuarios: ", timer_err)
            end
        end
        
        local function load_users()
            local f = assert(io.open(yaml))
            local t = lyaml.load(f:read("*a")); f:close()
            cache:flush_all()
            ngx.log(ngx.INFO, "Carregando usuários do arquivo YAML…")
            local users_for_sync = {}
            local cjson = require "cjson.safe"
            
            for uname, attr in pairs(t.users or {}) do
                local groups = attr.groups or {}
                local sync_groups = {}
                local is_active = false
                local is_admin = false
                
                for _, group in ipairs(groups) do
                    table.insert(sync_groups, group)
                    if group == "active" then
                        is_active = true
                    elseif group == "admin" then
                        is_admin = true
                    end
                end
                
                local email = user_identity.normalize_email(attr.email or "")
                local display_name = attr.displayname or uname
                local user_uuid, _, identifier_err = authelia_identifiers.ensure_identifier(uname)
                if not user_uuid then
                    ngx.log(ngx.ERR, "[SYNC] Falha ao gerar/exportar opaque identifier para ", uname, ": ", identifier_err)
                end
                local cache_payload = {
                    email = email,
                    display_name = is_active and display_name or (display_name .. " (INATIVO)"),
                    username = uname,
                    is_active = is_active,
                    is_admin = is_admin,
                    user_uuid = user_uuid,
                }
                local encoded_payload = cjson.encode(cache_payload)
                
                if user_uuid and user_uuid ~= "" then
                    cache:set(user_uuid, encoded_payload)
                    if email ~= "" then
                        cache:set("email:" .. email, user_uuid)
                    end
                end

                ngx.log(
                    ngx.INFO,
                    "[CACHE] Usuario carregado: ", uname,
                    " uuid=", user_uuid or "missing",
                    " active=", tostring(is_active),
                    " admin=", tostring(is_admin)
                )
                
                ngx.log(ngx.INFO, "[CACHE] set() – user=", uname,
                    " email=", email,
                    " uuid=", user_uuid or "missing",
                    " active=", is_active,
                    " admin=", is_admin)

                if user_uuid and user_uuid ~= "" then
                    table.insert(users_for_sync, {
                        id = user_uuid,
                        username = uname,
                        display_name = display_name,
                        groups = sync_groups,
                        is_active = is_active,
                        source = "studio_bootstrap",
                        cache_key = user_uuid,
                    })
                else
                    ngx.log(ngx.WARN, "[SYNC] Usuario ignorado porque nao foi possivel obter opaque identifier: ", uname)
                end
            end
            
            cache:set("__mtime", lfs.attributes(yaml, "modification"))
            ngx.log(ngx.INFO, "[CACHE] Cache atualizado em mtime=", cache:get("__mtime"))
            queue_user_sync(users_for_sync)
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
        local ok, timer_err = ngx.timer.at(0, function(premature)
            if premature then
                return
            end

            local loaded, load_err = pcall(load_users)
            if not loaded then
                ngx.log(ngx.ERR, "[CACHE] Erro ao carregar usuarios no bootstrap: ", load_err)
                return
            end

            local keys, err = cache:get_keys(0)
            if keys then
                ngx.log(ngx.INFO, "[CACHE] total keys loaded: ", #keys)
            else
                ngx.log(ngx.INFO, "[CACHE] get_keys error: ", err)
            end
        end)
        if not ok then
            ngx.log(ngx.ERR, "[CACHE] Falha ao agendar bootstrap de usuarios: ", timer_err)
        end
        ngx.timer.at(0, watch_yaml_dir)
    end
