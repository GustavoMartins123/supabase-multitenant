local groups = ngx.var.authelia_groups or ""
local email = ngx.var.authelia_email or ""
local user_context_headers = require "user_context_headers"
local groups_clean = groups:gsub("[%[%]]", "")
local is_admin = false
for group in groups_clean:gmatch("[^,]+") do
    if group:match("^%s*admin%s*$") then
        is_admin = true
        break
    end
end

if email ~= "" then
    user_context_headers.apply(email, groups)
end

if not is_admin then
    ngx.log(ngx.ERR, "[ADMIN] Access denied - not admin. Groups: ", groups)
    local method = ngx.var.request_method
    if method == "GET" then
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    else
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say('{"error": "Access denied"}')
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end
end
