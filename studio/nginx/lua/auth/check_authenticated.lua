local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Not authenticated")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local user_context_headers = require "user_context_headers"
user_context_headers.apply(email, ngx.var.authelia_groups or "")
