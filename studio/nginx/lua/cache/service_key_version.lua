local cache = ngx.shared.service_keys

local M = {}

local LOCK_TTL_SECONDS = 1
local LOCK_ATTEMPTS = 25

local function required_key(project_ref)
    return "service_key:required_version:" .. project_ref
end

local function cached_key(project_ref)
    return "service_key:cached_version:" .. project_ref
end

local function value_key(project_ref)
    return "service_key:value:" .. project_ref
end

local function checked_key(project_ref)
    return "service_key:checked_version:" .. project_ref
end

local function fetch_error_key(project_ref)
    return "service_key:fetch_error:" .. project_ref
end

local function with_project_lock(project_ref, callback)
    local lock_key = "service_key:version_lock:" .. project_ref

    for _ = 1, LOCK_ATTEMPTS do
        local acquired, err = cache:add(lock_key, true, LOCK_TTL_SECONDS)
        if acquired then
            -- As operacoes do callback nao cedem o event loop. Assim o lock
            -- cobre atomicamente a promocao da versao e a troca da chave.
            local ok, first, second, third = pcall(callback)
            cache:delete(lock_key)
            if not ok then
                ngx.log(ngx.ERR, "Falha ao atualizar versao da service key: ", first)
                return nil, "version_update_failed"
            end
            return first, second, third
        end
        if err ~= "exists" then
            ngx.log(ngx.ERR, "Falha ao adquirir lock da service key: ", err)
            return nil, "version_lock_failed"
        end
        ngx.sleep(0.001)
    end

    ngx.log(ngx.WARN, "Timeout no lock de versao da service key para ", project_ref)
    return nil, "version_lock_timeout"
end

function M.promote(project_ref, candidate)
    candidate = tonumber(candidate)
    if not candidate or candidate < 1 then
        return nil, "invalid_version"
    end

    return with_project_lock(project_ref, function()
        local key = required_key(project_ref)
        local current = tonumber(cache:get(key)) or 0
        if candidate > current then
            local stored, err = cache:set(key, candidate)
            if not stored then
                error(err or "required_version_store_failed")
            end
            current = candidate
        end
        return current
    end)
end

function M.read_cached(project_ref)
    return with_project_lock(project_ref, function()
        local minimum = tonumber(cache:get(required_key(project_ref))) or 0
        local value = cache:get(value_key(project_ref))
        local version = tonumber(cache:get(cached_key(project_ref))) or 0
        if value and version >= minimum then
            return value, "hit", minimum
        end
        if value then
            cache:delete(value_key(project_ref))
            cache:delete(cached_key(project_ref))
            return nil, "stale", minimum
        end
        return nil, "miss", minimum
    end)
end

function M.publish(project_ref, value, version, cache_ttl, checked_ttl)
    version = tonumber(version)
    if not version or version < 1 then
        return nil, "invalid_version"
    end

    return with_project_lock(project_ref, function()
        local minimum = tonumber(cache:get(required_key(project_ref))) or 0
        if version < minimum then
            return false, minimum
        end
        if version > minimum then
            minimum = version
            local promoted, promote_err = cache:set(required_key(project_ref), minimum)
            if not promoted then
                error(promote_err or "required_version_store_failed")
            end
        end

        local value_stored, value_err = cache:set(value_key(project_ref), value, cache_ttl)
        if not value_stored then
            error(value_err or "service_key_store_failed")
        end
        local version_stored, version_err = cache:set(
            cached_key(project_ref),
            version,
            cache_ttl
        )
        if not version_stored then
            cache:delete(value_key(project_ref))
            error(version_err or "cached_version_store_failed")
        end
        cache:set(checked_key(project_ref), minimum, checked_ttl)
        cache:delete(fetch_error_key(project_ref))
        return true, minimum
    end)
end

function M.invalidate(project_ref, version, checked_ttl)
    version = tonumber(version)
    if not version or version < 1 then
        return nil, "invalid_version"
    end

    return with_project_lock(project_ref, function()
        local minimum = tonumber(cache:get(required_key(project_ref))) or 0
        if version > minimum then
            minimum = version
            local promoted, promote_err = cache:set(required_key(project_ref), minimum)
            if not promoted then
                error(promote_err or "required_version_store_failed")
            end
        end

        local cached_version = tonumber(cache:get(cached_key(project_ref))) or 0
        if cached_version < minimum then
            cache:delete(value_key(project_ref))
            cache:delete(cached_key(project_ref))
        end
        cache:delete(fetch_error_key(project_ref))
        cache:set(checked_key(project_ref), minimum, checked_ttl)
        return minimum
    end)
end

return M
