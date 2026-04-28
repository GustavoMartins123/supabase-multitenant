local user_context_headers = require "user_context_headers"
local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Email não disponível para hashing.")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

user_context_headers.apply(email, ngx.var.authelia_groups or "")
