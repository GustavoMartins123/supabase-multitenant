local email = ngx.var.authelia_email
local groups = ngx.var.authelia_groups or ""

if not email or email == "" then
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local is_admin = string.find(groups, "admin") ~= nil
if not is_admin then
    ngx.log(ngx.ERR, "[ALL-USERS] User not admin: ", email, " groups: ", groups)
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

local sha256 = require "resty.sha256"
local str = require "resty.string"
local hasher = sha256:new()
hasher:update(email)
local digest = hasher:final()
local email_hash = str.to_hex(digest)

ngx.req.set_header("Remote-Email", email_hash)
ngx.req.set_header("Remote-Groups", groups)
