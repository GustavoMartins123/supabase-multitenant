local user_identity = require "user_identity"

return user_identity.hash_email(ngx.var.authelia_email or "")
