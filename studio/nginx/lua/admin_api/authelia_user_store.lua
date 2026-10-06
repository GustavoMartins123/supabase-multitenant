local lyaml = require("lyaml")
local file_store = require("admin_api.authelia_file_store")

local M = {}

local YAML_PATH = "/config/users_database.yml"
local LOCK_RESOURCE = "users_database.yml"
local FILE_MODE = 438 -- 0666; compartilhado com o container Authelia.

local function read_raw()
    local handle, err = io.open(YAML_PATH, "rb")
    if not handle then
        return nil, err
    end
    local content = handle:read("*a") or ""
    handle:close()
    return content
end

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

    return file_store.atomic_write(YAML_PATH, serialized, FILE_MODE)
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
    return file_store.atomic_write(YAML_PATH, original, FILE_MODE)
end

function M.with_lock(callback)
    return file_store.with_lock(LOCK_RESOURCE, callback)
end

return M
