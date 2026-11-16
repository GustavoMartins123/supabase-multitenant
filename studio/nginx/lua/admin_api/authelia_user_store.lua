local lyaml = require("lyaml")
local file_store = require("admin_api.authelia_file_store")

local M = {}

local YAML_PATH = "/config/users_database.yml"
local LOCK_RESOURCE = "users_database.yml"
local FILE_MODE = 384 -- 0600; arquivo gerenciado por uid compartilhado (nobody/65534).
local REPUBLISH_DELAY_SECONDS = 1.1
local REPUBLISH_CACHE_KEY = "__yaml_republish_after"

local function read_raw()
    local handle, err = io.open(YAML_PATH, "rb")
    if not handle then
        return nil, err
    end
    local content = handle:read("*a") or ""
    handle:close()
    return content
end

M.read_raw = read_raw

local function parse(content)
    local ok, data = pcall(lyaml.load, content)
    if not ok or type(data) ~= "table" then
        return nil, "invalid users database"
    end
    if data.users == nil then
        data.users = {}
    elseif type(data.users) ~= "table" then
        return nil, "invalid users database users section"
    end
    return data
end

function M.load()
    local content, read_err = read_raw()
    if not content then
        return nil, nil, read_err
    end
    local data, parse_err = parse(content)
    if not data then
        return nil, nil, parse_err
    end
    return data, content
end

function M.write(data)
    if type(data) ~= "table" or type(data.users) ~= "table" then
        return nil, "invalid users database"
    end

    local dumped, serialized = pcall(lyaml.dump, { data })
    if not dumped or type(serialized) ~= "string" then
        return nil, serialized or "failed to serialize users database"
    end

    local reparsed, parse_err = parse(serialized)
    if not reparsed then
        return nil, parse_err
    end

    local ok, write_err, dir_err = file_store.atomic_write(YAML_PATH, serialized, FILE_MODE)
    if ok then
        M.schedule_republish()
    end
    return ok, write_err, dir_err
end

function M.restore(original)
    if type(original) ~= "string" then
        return nil, "invalid rollback snapshot"
    end
    local _, parse_err = parse(original)
    if parse_err then
        return nil,
            "refusing to restore invalid users database snapshot: " .. parse_err
    end
    local ok, write_err, dir_err = file_store.atomic_write(YAML_PATH, original, FILE_MODE)
    if ok then
        M.schedule_republish()
    end
    return ok, write_err, dir_err
end

function M.flush_republish(force)
    local cache = ngx and ngx.shared and ngx.shared.users_cache
    if not force and cache then
        local pending = tonumber(cache:get(REPUBLISH_CACHE_KEY))
        if not pending or pending > ngx.now() then
            return false
        end
    end
    return file_store.with_lock(LOCK_RESOURCE, function()
        if cache and not force then
            local pending = tonumber(cache:get(REPUBLISH_CACHE_KEY))
            if not pending or pending > ngx.now() then
                return false
            end
        end
        local current, raw = M.load()
        if current and raw then
            local ok, write_err = file_store.atomic_write(YAML_PATH, raw, FILE_MODE)
            if not ok then
                return nil, write_err
            end
        end
        if cache then
            cache:delete(REPUBLISH_CACHE_KEY)
        end
        return true
    end)
end

function M.schedule_republish()
    local cache = ngx and ngx.shared and ngx.shared.users_cache
    if not cache or not ngx or type(ngx.now) ~= "function" then
        return
    end
    cache:set(REPUBLISH_CACHE_KEY, ngx.now() + REPUBLISH_DELAY_SECONDS)
    if ngx.timer and type(ngx.timer.at) == "function" then
        ngx.timer.at(REPUBLISH_DELAY_SECONDS, function(premature)
            if premature then
                return
            end
            M.flush_republish(false)
        end)
    end
end

function M.with_lock(callback)
    return file_store.with_lock(LOCK_RESOURCE, callback)
end

return M
