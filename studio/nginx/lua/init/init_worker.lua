        local lfs = require("lfs")
        local cjson = require("cjson.safe")
        local user_identity = require("project_context.user_identity")
        local authelia_identifiers = require("admin_api.authelia_identifiers")
        local user_store = require("admin_api.authelia_user_store")
        local user_sync = require("admin_api.user_sync")
        local cache = ngx.shared.users_cache
        local yaml = "/config/users_database.yml"
        local max_bootstrap_attempts = 20

        local function group_state(groups)
            local active = false
            local admin = false
            for _, group in ipairs(groups or {}) do
                if group == "active" then
                    active = true
                elseif group == "admin" then
                    admin = true
                end
            end
            return active, admin
        end

        local function groups_equal(left, right)
            local counts = {}
            local left_count = 0
            local right_count = 0
            for _, group in ipairs(left or {}) do
                counts[group] = (counts[group] or 0) + 1
                left_count = left_count + 1
            end
            for _, group in ipairs(right or {}) do
                counts[group] = (counts[group] or 0) - 1
                right_count = right_count + 1
            end
            if left_count ~= right_count then
                return false
            end
            for _, count in pairs(counts) do
                if count ~= 0 then
                    return false
                end
            end
            return true
        end

        local function snapshot_still_current(payload, user)
            if type(user) ~= "table" or user.disabled == true then
                return false
            end
            local active = group_state(user.groups)
            local display_name = user.displayname or payload.username
            return display_name == payload.display_name
                and active == payload.is_active
                and groups_equal(user.groups, payload.groups)
        end

        local function queue_user_sync(users_for_sync)
            if ngx.worker.id() ~= 0 or not users_for_sync or #users_for_sync == 0 then
                return
            end

            local ok, timer_err = ngx.timer.at(0, function(premature, payloads)
                if premature then
                    return
                end

                local synced = 0
                local skipped = 0
                for _, payload in ipairs(payloads) do
                    -- Revalida o snapshot e faz o sync sob o mesmo lock das
                    -- mutacoes. Assim um timer antigo nunca pode sobrescrever
                    -- no backend uma ativacao/desativacao/perfil mais recente.
                    local outcome, lock_err = user_store.with_lock(function()
                        local current, _, load_err = user_store.load()
                        if not current then
                            return { error = load_err or "users database unavailable" }
                        end

                        local current_user = current.users[payload.username]
                        if not snapshot_still_current(payload, current_user) then
                            return { skipped = true }
                        end

                        local sync_result, sync_err = user_sync.sync_user(payload)
                        if sync_err then
                            return { error = sync_err }
                        end

                        if type(sync_result) == "table" and sync_result.id then
                            local cached_json = cache:get(payload.cache_key)
                            local cached_user = cached_json and cjson.decode(cached_json)
                            if type(cached_user) == "table"
                                and cached_user.username == payload.username
                            then
                                cached_user.user_uuid = sync_result.id
                                local encoded = cjson.encode(cached_user)
                                if encoded then
                                    cache:set(payload.cache_key, encoded)
                                    cache:set(sync_result.id, encoded)
                                    if cached_user.email and cached_user.email ~= "" then
                                        cache:set(
                                            "email:" .. cached_user.email,
                                            sync_result.id
                                        )
                                    end
                                end
                            end
                        end

                        return { synced = true }
                    end)

                    if not outcome then
                        ngx.log(
                            ngx.ERR,
                            "[SYNC] Falha ao serializar sync do usuario ",
                            payload.username,
                            ": ",
                            lock_err
                        )
                    elseif outcome.error then
                        ngx.log(
                            ngx.ERR,
                            "[SYNC] Falha ao sincronizar usuario ",
                            payload.username,
                            ": ",
                            outcome.error
                        )
                    elseif outcome.skipped then
                        skipped = skipped + 1
                        ngx.log(
                            ngx.INFO,
                            "[SYNC] Snapshot obsoleto ignorado para usuario ",
                            payload.username
                        )
                    elseif outcome.synced then
                        synced = synced + 1
                    end
                end

                ngx.log(
                    ngx.INFO,
                    "[SYNC] Usuarios sincronizados com backend: ",
                    synced,
                    "/",
                    #payloads,
                    " (snapshots obsoletos ignorados=",
                    skipped,
                    ")"
                )
            end, users_for_sync)

            if not ok then
                ngx.log(
                    ngx.ERR,
                    "[SYNC] Falha ao agendar sincronizacao de usuarios: ",
                    timer_err
                )
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

        local function load_users_locked()
            -- O snapshot e lido somente depois de adquirir o mesmo flock usado
            -- pelos endpoints de criacao/ativacao/desativacao/perfil. O lock e
            -- liberado automaticamente pelo kernel se o worker morrer.
            local t, _, load_err = user_store.load()
            if not t then
                return nil, load_err or "falha ao carregar users_database.yml"
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
                    local is_active, is_admin = group_state(groups)

                    for _, group in ipairs(groups) do
                        table.insert(sync_groups, group)
                    end

                    local email = user_identity.normalize_email(attr.email or "")
                    local display_name = attr.displayname or uname
                    -- Ordem global de locks: users_database.yml -> ids.yml.
                    local user_uuid, _, identifier_err =
                        authelia_identifiers.ensure_identifier(uname)
                    if not user_uuid then
                        missing_identifiers = missing_identifiers + 1
                        ngx.log(
                            ngx.ERR,
                            "[SYNC] Falha ao gerar/exportar opaque identifier para ",
                            uname,
                            ": ",
                            identifier_err
                        )
                    else
                        local cache_payload = {
                            email = email,
                            display_name = is_active
                                and display_name
                                or (display_name .. " (INATIVO)"),
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
                        "[CACHE] Usuario preparado: ",
                        uname,
                        " uuid=",
                        user_uuid or "missing",
                        " active=",
                        tostring(is_active),
                        " admin=",
                        tostring(is_admin)
                    )
                end
            end

            if missing_identifiers > 0 then
                return nil,
                    "falha ao obter opaque identifier para "
                    .. missing_identifiers
                    .. " usuario(s)"
            end

            local old_keys = previously_managed_keys()
            local manifest = {}
            for key, value in pairs(snapshot) do
                local stored, store_err = cache:set(key, value)
                if not stored then
                    return nil,
                        "falha ao publicar chave "
                        .. key
                        .. ": "
                        .. (store_err or "erro desconhecido")
                end
                manifest[#manifest + 1] = key
            end

            for key in pairs(old_keys) do
                if snapshot[key] == nil then
                    cache:delete(key)
                end
            end
            table.sort(manifest)
            cache:set("__yaml_user_keys", cjson.encode(manifest))
            cache:set("__mtime", lfs.attributes(yaml, "modification"))
            ngx.log(
                ngx.INFO,
                "[CACHE] Snapshot atualizado em mtime=",
                cache:get("__mtime")
            )

            return users_for_sync
        end

        local function load_users()
            local users_for_sync, load_err = user_store.with_lock(load_users_locked)
            if not users_for_sync then
                return nil, load_err
            end
            queue_user_sync(users_for_sync)
            return true
        end

        local function watch_yaml_dir(premature)
            if premature then
                return
            end
            local pipe = require("ngx.pipe")
            local watch_dir = "/config/"
            local target_file = "users_database.yml"
            local proc, err = pipe.spawn({
                "inotifywait",
                "-q",
                "-m",
                "-e",
                "close_write,moved_to",
                watch_dir,
            })

            if not proc then
                ngx.log(
                    ngx.ERR,
                    "[INOTIFY-PIPE] Falha ao iniciar inotifywait: ",
                    err
                )
                return
            end

            ngx.log(
                ngx.INFO,
                "[INOTIFY-PIPE] Monitoramento iniciado no diretório: ",
                watch_dir
            )

            local function read_events()
                while true do
                    local line, read_err = proc:stdout_read_line()
                    if line then
                        -- Reage somente ao basename final. Temporarios
                        -- users_database.yml.tmp.* e arquivos .lock nao entram.
                        if line:sub(-#target_file) == target_file then
                            ngx.log(
                                ngx.INFO,
                                "[INOTIFY-PIPE] Arquivo modificado: ",
                                line
                            )
                            ngx.sleep(0.1)

                            local called, loaded, reload_err = pcall(load_users)
                            if not called or not loaded then
                                ngx.log(
                                    ngx.ERR,
                                    "[INOTIFY-PIPE] Erro ao recarregar usuários: ",
                                    called and reload_err or loaded
                                )
                            end
                        end
                    elseif read_err == "closed" then
                        ngx.log(
                            ngx.INFO,
                            "[INOTIFY-PIPE] Processo inotifywait finalizado."
                        )
                        break
                    elseif read_err ~= "timeout" and read_err ~= nil then
                        ngx.log(
                            ngx.ERR,
                            "[INOTIFY-PIPE] Erro na leitura do pipe: ",
                            read_err
                        )
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
                            local next_delay = math.min(
                                30,
                                math.max(1, attempt * 2)
                            )
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
                            ngx.log(
                                ngx.ERR,
                                "[CACHE] Bootstrap de usuarios falhou apos ",
                                attempt,
                                " tentativas: ",
                                err
                            )
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
                    ngx.log(
                        ngx.ERR,
                        "[CACHE] Falha ao agendar bootstrap de usuarios: ",
                        timer_err
                    )
                end
            end

            schedule_bootstrap(0, 1)
            ngx.timer.at(0, watch_yaml_dir)
        end
