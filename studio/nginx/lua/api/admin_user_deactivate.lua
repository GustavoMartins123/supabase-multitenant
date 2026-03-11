local user_id = ngx.var[1]

local cache = ngx.shared.users_cache
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

local user_entry = yaml_data.users[username]
if not user_entry then
    ngx.log(ngx.ERR, "[DEACTIVATE] User not found in YAML: ", username)
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.say('{"error": "User not found in database"}')
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

do
    local sha2 = require "resty.sha256"
    local str  = require "resty.string"
    local h    = sha2:new()
    h:update((ngx.var.authelia_email or ""):lower():gsub("%s+", ""))
    local caller_id = str.to_hex(h:final())

    local target_is_me    = (caller_id == user_id)

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
local new_groups = {}
for _, g in ipairs(user_entry.groups) do
    if g ~= "active" then
        table.insert(new_groups, g)
    end
end
table.insert(new_groups, "inactive")
user_entry.groups = new_groups

local updated_yaml = lyaml.dump({ yaml_data })
local f_write, err_write = io.open(yaml_path, "w")
if not f_write then
    ngx.log(ngx.ERR, "[DEACTIVATE] Failed to write YAML: ", err_write)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to update user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end
f_write:write(updated_yaml)
f_write:close()

user.is_active = false
cache:set(user_id, cjson.encode(user))

ngx.log(ngx.ERR, "[DEACTIVATE] Successfully deactivated user: ", username)

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    message = "User deactivated successfully",
    user = {
        id = user_id,
        username = username,
        display_name = user.display_name,
        status = "deactivated"
    },
    timestamp = os.time()
}))
return ngx.exit(ngx.HTTP_OK)
