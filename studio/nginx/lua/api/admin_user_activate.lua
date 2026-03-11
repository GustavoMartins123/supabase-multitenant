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
local new_groups = {}
for _, g in ipairs(user_entry.groups) do
    if g ~= "inactive" then
        table.insert(new_groups, g)
    end
end
table.insert(new_groups, "active")
user_entry.groups = new_groups

local updated_yaml = lyaml.dump({ yaml_data })
local f_write, err_write = io.open(yaml_path, "w")
if not f_write then
    ngx.log(ngx.ERR, "[ACTIVATE] Failed to write YAML: ", err_write)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to update user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end
f_write:write(updated_yaml)
f_write:close()

user.is_active = true
cache:set(user_id, cjson.encode(user))

ngx.log(ngx.ERR, "[ACTIVATE] Successfully activated user: ", username)

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    message = "User activated successfully",
    user = {
        id = user_id,
        username = username,
        display_name = user.display_name,
        status = "active"
    },
    timestamp = os.time()
}))
return ngx.exit(ngx.HTTP_OK)
