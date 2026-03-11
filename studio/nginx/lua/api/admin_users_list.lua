local cjson = require "cjson.safe"
local cache = ngx.shared.users_cache
local keys, err = cache:get_keys(0)

if not keys then
    ngx.log(ngx.ERR, "[ADMIN-USERS] cache:get_keys error: ", err)
    ngx.say('{"error": "Failed to fetch users"}')
    return ngx.exit(500)
end

local users = {}
local active_count = 0
local inactive_count = 0

for _, key in ipairs(keys) do
    if key ~= "__mtime" then
        local user_data = cache:get(key)
        if user_data then
            local user = cjson.decode(user_data)
            if user then
                if not user.is_admin then
                    local safe_user = {
                        id = key,
                        username = user.username,
                        display_name = user.display_name,
                        is_active = user.is_active,
                        status = user.is_active and "active" or "inactive",
                        email_hint = user.email and (
                            user.email:sub(1,1) .. "***@" .. 
                            user.email:match("@(.+)$"):gsub("^(.)", "%1***")
                        ) or "unknown"
                    }
                    
                    table.insert(users, safe_user)
                    
                    if user.is_active then
                        active_count = active_count + 1
                    else
                        inactive_count = inactive_count + 1
                    end
                end
            end
        end
    end
end

table.sort(users, function(a, b)
    if a.is_active ~= b.is_active then
        return a.is_active
    end
    return a.username < b.username
end)

local response = {
    users = users,
    summary = {
        total = #users,
        active = active_count,
        inactive = inactive_count
    },
    timestamp = os.time()
}

ngx.header.content_type = "application/json"
ngx.say(cjson.encode(response))
