        local lyaml = require("lyaml")
        local lfs = require("lfs")
        local cjson = require("cjson.safe")
        local user_identity = require("project_context.user_identity")
        local authelia_identifiers = require("admin_api.authelia_identifiers")
        local user_sync = require("admin_api.user_sync")
        local cache = ngx.shared.users_cache
        local yaml = "/config/users_database.yml"
        local max_bootstrap_attempts = 20

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
                            local cjson = require("cjson.safe")
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
        
        local function previously_managed_keys()
            local managed = {}
            local manifest = cjson.decode(cache:get("__yaml_user_keys") or "")
            if type(manifest) == "table" then
                for _, key in ipairs(manifest) do
                    if type(key) == "string" then
                        managed[key] = true
                    end
                end
                return managed
            end

            -- Compatibilidade com o primeiro reload depois do upgrade, quando
            -- ainda nao existe manifesto das chaves publicadas pelo YAML.
            local keys = cache:get_keys(0) or {}
            for _, key in ipairs(keys) do
                if key:match("^email:") then
                    managed[key] = true
                elseif not key:match("^__") then
                    local value = cache:get(key)
                    local decoded = type(value) == "string" and cjson.decode(value)
                    if type(decoded) == "table"
                        and decoded.username
                        and decoded.user_uuid
                    then
                        managed[key] = true
                    end
                end
            end
            return managed
        end

        local function load_users()
            local f = assert(io.open(yaml))
            local content = f:read("*a")
            f:close()
            local t = lyaml.load(content)
            if type(t) ~= "table" or type(t.users) ~= "table" then
                return nil, "estrutura invalida no users_database.yml"
            end

            ngx.log(ngx.INFO, "Preparando snapshot de usuários do arquivo YAML…")
            local snapshot = {}
            local users_for_sync = {}
            local missing_identifiers = 0

            local function is_bootstrap_placeholder(uname)
                return uname == "__bootstrap_placeholder__"
            end

            for uname, attr in pairs(t.users) do
                if type(attr) ~= "table" then
                    return nil, "registro invalido para usuario " .. tostring(uname)
                end
                if attr.disabled == true or is_bootstrap_placeholder(uname) then
                    ngx.log(ngx.INFO, "[CACHE] Usuario ignorado no bootstrap: ", uname)
                else
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
                        missing_identifiers = missing_identifiers + 1
                        ngx.log(ngx.ERR, "[SYNC] Falha ao gerar/exportar opaque identifier para ", uname, ": ", identifier_err)
                    else
                        local cache_payload = {
                            email = email,
                            display_name = is_active and display_name or (display_name .. " (INATIVO)"),
                            username = uname,
                            is_active = is_active,
                            is_admin = is_admin,
                            user_uuid = user_uuid,
                            picture = attr.picture or "",
                        }
                        local encoded_payload = cjson.encode(cache_payload)
                        if not encoded_payload then
                            return nil, "falha ao serializar usuario " .. uname
                        end

                        snapshot[user_uuid] = encoded_payload
                        if email ~= "" then
                            snapshot["email:" .. email] = user_uuid
                        end
                        table.insert(users_for_sync, {
                            id = user_uuid,
                            username = uname,
                            display_name = display_name,
                            groups = sync_groups,
                            is_active = is_active,
                            source = "studio_bootstrap",
                            cache_key = user_uuid,
                        })
                    end

                    ngx.log(
                        ngx.INFO,
                        "[CACHE] Usuario preparado: ", uname,
                        " uuid=", user_uuid or "missing",
                        " active=", tostring(is_active),
                        " admin=", tostring(is_admin)
                    )
                end
            end

            if missing_identifiers > 0 then
                return nil, "falha ao obter opaque identifier para " .. missing_identifiers .. " usuario(s)"
            end

            -- Publica primeiro todas as entradas novas. Requests concorrentes
            -- continuam vendo o snapshot anterior ate cada chave ser trocada.
            local old_keys = previously_managed_keys()
            local manifest = {}
            for key, value in pairs(snapshot) do
                local stored, store_err = cache:set(key, value)
                if not stored then
                    return nil, "falha ao publicar chave " .. key .. ": " .. (store_err or "erro desconhecido")
                end
                manifest[#manifest + 1] = key
            end

            -- Somente depois da publicacao remove usuarios/emails que sairam
            -- do YAML, eliminando a janela global de cache vazio.
            for key in pairs(old_keys) do
                if snapshot[key] == nil then
                    cache:delete(key)
                end
            end
            table.sort(manifest)
            cache:set("__yaml_user_keys", cjson.encode(manifest))
            cache:set("__mtime", lfs.attributes(yaml, "modification"))
            ngx.log(ngx.INFO, "[CACHE] Snapshot atualizado em mtime=", cache:get("__mtime"))
            queue_user_sync(users_for_sync)
            return true
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
                        
                        local called, loaded, load_err = pcall(load_users)
                        if not called or not loaded then
                            ngx.log(
                                ngx.ERR,
                                "[INOTIFY-PIPE] Erro ao recarregar usuários: ",
                                called and load_err or loaded
                            )
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
        local function schedule_bootstrap(delay, attempt)
            local ok, timer_err = ngx.timer.at(delay, function(premature)
                if premature then
                    return
                end

                local loaded, load_ok, load_err = pcall(load_users)
                if not loaded or not load_ok then
                    local err = loaded and load_err or load_ok
                    if attempt < max_bootstrap_attempts then
                        local next_delay = math.min(30, math.max(1, attempt * 2))
                        ngx.log(
                            ngx.WARN,
                            "[CACHE] Bootstrap de usuarios falhou na tentativa ",
                            attempt,
                            "/",
                            max_bootstrap_attempts,
                            ": ",
                            err or "erro desconhecido",
                            ". Tentando novamente em ",
                            next_delay,
                            "s"
                        )
                        schedule_bootstrap(next_delay, attempt + 1)
                    else
                        ngx.log(ngx.ERR, "[CACHE] Bootstrap de usuarios falhou apos ", attempt, " tentativas: ", err)
                    end
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
        end

        schedule_bootstrap(0, 1)
        ngx.timer.at(0, watch_yaml_dir)
    end
