local groups = ngx.var.authelia_groups or ""
local email = ngx.var.authelia_email or ""
local admin_groups = require("security.admin_groups")
local user_context_headers = require("project_context.user_context_headers")
local is_admin = admin_groups.is_admin(groups)

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
