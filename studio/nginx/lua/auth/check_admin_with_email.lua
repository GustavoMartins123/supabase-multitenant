local email = ngx.var.authelia_email
local groups = ngx.var.authelia_groups or ""
local user_context_headers = require "user_context_headers"

if not email or email == "" then
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local is_admin = string.find(groups, "admin") ~= nil
if not is_admin then
    ngx.log(ngx.ERR, "[ALL-USERS] User not admin: ", email, " groups: ", groups)
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

user_context_headers.apply(email, groups)
