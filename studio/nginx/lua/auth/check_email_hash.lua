local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Email não disponível para hashing.")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local sha256 = require "resty.sha256"
local str    = require "resty.string"
local hasher = sha256:new()
hasher:update(email)
local digest = hasher:final()
local email_hash = str.to_hex(digest)

ngx.req.set_header("Remote-Email", email_hash)
ngx.req.set_header("Remote-Groups", ngx.var.authelia_groups or "")
