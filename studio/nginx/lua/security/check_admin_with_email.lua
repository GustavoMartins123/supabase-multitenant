local email = ngx.var.authelia_email
local groups = ngx.var.authelia_groups or ""
local user_context_headers = require("project_context.user_context_headers")

if not email or email == "" then
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local groups_clean = groups:gsub("[%[%]]", "")
local is_admin = false
for group in groups_clean:gmatch("[^,]+") do
    if group:match("^%s*admin%s*$") then
        is_admin = true
        break
    end
end
if not is_admin then
    ngx.log(ngx.ERR, "[ALL-USERS] User not admin: ", email, " groups: ", groups)
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

user_context_headers.apply(email, groups)
