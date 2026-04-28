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
    ngx.log(ngx.ERR, "[DEACTIVATE] Failed to open YAML: ", err)
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
    ngx.log(ngx.ERR, "[DEACTIVATE] User not found in YAML: ", username)
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.say('{"error": "User not found in database"}')
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

do
    local caller_id = ngx.req.get_headers()["X-User-Id"] or ""
    local target_is_me = caller_id ~= "" and (
        caller_id == tostring(user.user_uuid or "")
        or caller_id == user_id
    )

    local target_is_admin = false
    for _, g in ipairs(user_entry.groups or {}) do
        if g == "admin" then
        target_is_admin = true
        break
        end
    end

    if target_is_me then
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say('{"error":"You cannot deactivate yourself"}')
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end

    if target_is_admin then
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say('{"error":"Cannot deactivate an admin user"}')
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end
end

if user_entry.groups then
    local has_inactive = false
    for _, g in ipairs(user_entry.groups) do
        if g == "inactive" then
            has_inactive = true
            break
        end
    end
    if has_inactive then
        ngx.status = ngx.HTTP_OK
        ngx.say('{"message": "User is already inactive"}')
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
    if g ~= "active" then
        table.insert(new_groups, g)
    end
end
table.insert(new_groups, "inactive")
user_entry.groups = new_groups

local ok_write, err_write = write_yaml_file(yaml_path, yaml_data)
if not ok_write then
    ngx.log(ngx.ERR, "[DEACTIVATE] Failed to write YAML: ", err_write)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to update user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

user.is_active = false

if not user.user_uuid or user.user_uuid == "" then
    local ensured_user_uuid, _, identifier_err = authelia_identifiers.ensure_identifier(username)
    if not ensured_user_uuid then
        ngx.log(ngx.ERR, "[DEACTIVATE] Failed to generate/export Authelia identifier: ", identifier_err)
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
    is_active = false
})

if sync_err then
    ngx.log(ngx.ERR, "[DEACTIVATE] Failed to sync user with backend: ", sync_err)
    user_entry.groups = original_groups
    write_yaml_file(yaml_path, yaml_data)
    ngx.status = ngx.HTTP_BAD_GATEWAY
    ngx.say('{"error": "User deactivated in Authelia but failed to sync with backend"}')
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

ngx.log(ngx.ERR, "[DEACTIVATE] Successfully deactivated user: ", username)

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    message = "User deactivated successfully",
    user = {
        id = sync_result and sync_result.id or user.user_uuid or user_id,
        username = username,
        display_name = user.display_name,
        status = "deactivated"
    },
    timestamp = os.time()
}))
return ngx.exit(ngx.HTTP_OK)
