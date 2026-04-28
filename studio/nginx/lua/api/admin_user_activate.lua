local user_id = ngx.var[1]

local cache = ngx.shared.users_cache
local authelia_identifiers = require "authelia_identifiers"
local user_sync = require "user_sync"
local user_data = cache:get(user_id)
if not user_data then
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.say('{"error": "User not found"}')
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

local cjson = require "cjson.safe"
local user = cjson.decode(user_data)
if not user then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid user data"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local username = user.username

local lyaml = require "lyaml"
local yaml_path = "/config/users_database.yml"
local f, err = io.open(yaml_path, "r")
if not f then
    ngx.log(ngx.ERR, "[ACTIVATE] Failed to open YAML: ", err)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to read user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local content = f:read("*a")
f:close()

local yaml_data = lyaml.load(content)
if not yaml_data or not yaml_data.users then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid YAML structure"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local function write_yaml_file(path, data)
    local serialized = lyaml.dump({ data })
    local handle, write_err = io.open(path, "w")
    if not handle then
        return nil, write_err
    end
    handle:write(serialized)
    handle:close()
    return true
end

local user_entry = yaml_data.users[username]
if not user_entry then
    ngx.log(ngx.ERR, "[ACTIVATE] User not found in YAML: ", username)
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.say('{"error": "User not found in database"}')
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

if user_entry.groups then
    local has_active = false
    for _, g in ipairs(user_entry.groups) do
        if g == "active" then
            has_active = true
            break
        end
    end
    if has_active then
        ngx.status = ngx.HTTP_OK
        ngx.say('{"message": "User is already active"}')
        return ngx.exit(ngx.HTTP_OK)
    end
end

user_entry.groups = user_entry.groups or {}
local original_groups = {}
for _, group_name in ipairs(user_entry.groups) do
    table.insert(original_groups, group_name)
end
local new_groups = {}
for _, g in ipairs(user_entry.groups) do
    if g ~= "inactive" then
        table.insert(new_groups, g)
    end
end
table.insert(new_groups, "active")
user_entry.groups = new_groups

local ok_write, err_write = write_yaml_file(yaml_path, yaml_data)
if not ok_write then
    ngx.log(ngx.ERR, "[ACTIVATE] Failed to write YAML: ", err_write)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to update user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

user.is_active = true

if not user.user_uuid or user.user_uuid == "" then
    local ensured_user_uuid, _, identifier_err = authelia_identifiers.ensure_identifier(username)
    if not ensured_user_uuid then
        ngx.log(ngx.ERR, "[ACTIVATE] Failed to generate/export Authelia identifier: ", identifier_err)
        user_entry.groups = original_groups
        write_yaml_file(yaml_path, yaml_data)
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        ngx.say('{"error": "Failed to generate Authelia opaque identifier"}')
        return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end
    user.user_uuid = ensured_user_uuid
end

local sync_result, sync_err = user_sync.sync_user({
    id = user.user_uuid,
    username = username,
    display_name = user.display_name,
    groups = user_entry.groups,
    is_active = true
})

if sync_err then
    ngx.log(ngx.ERR, "[ACTIVATE] Failed to sync user with backend: ", sync_err)
    user_entry.groups = original_groups
    write_yaml_file(yaml_path, yaml_data)
    ngx.status = ngx.HTTP_BAD_GATEWAY
    ngx.say('{"error": "User activated in Authelia but failed to sync with backend"}')
    return ngx.exit(ngx.HTTP_BAD_GATEWAY)
end

if sync_result and sync_result.id then
    user.user_uuid = sync_result.id
end

local encoded_user = cjson.encode(user)
cache:set(user_id, encoded_user)
if user.user_uuid and user.user_uuid ~= "" then
    cache:set(user.user_uuid, encoded_user)
end

ngx.log(ngx.ERR, "[ACTIVATE] Successfully activated user: ", username)

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    message = "User activated successfully",
    user = {
        id = sync_result and sync_result.id or user.user_uuid or user_id,
        user_hash = user_id,
        username = username,
        display_name = user.display_name,
        status = "active"
    },
    timestamp = os.time()
}))
return ngx.exit(ngx.HTTP_OK)
