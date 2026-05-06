local cjson = require "cjson.safe"
local lyaml = require "lyaml"

local yaml_path = "/config/users_database.yml"

local function has_admin(users)
    for _, user in pairs(users or {}) do
        if user.disabled ~= true then
            for _, group in ipairs(user.groups or {}) do
                if group == "admin" then
                    return true
                end
            end
        end
    end
    return false
end

if ngx.var.request_method ~= "GET" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local users = {}
local file = io.open(yaml_path, "r")
if file then
    local content = file:read("*a") or ""
    file:close()
    if content:gsub("%s+", "") ~= "" then
        local parsed = lyaml.load(content)
        if type(parsed) == "table" and type(parsed.users) == "table" then
            users = parsed.users
        end
    end
end

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    needs_admin = not has_admin(users)
}))