local sha256 = require "resty.sha256"
local str    = require "resty.string"
local email  = ngx.var.authelia_email or ""
local h = sha256:new()
h:update(email:lower():gsub("%s+", ""))
return str.to_hex(h:final())
