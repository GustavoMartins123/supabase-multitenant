local hmac  = require "resty.hmac"
local str   = require "resty.string"
local key = COOKIE_SECRET
local ref = ngx.var.arg_ref
if not ref or ref == "" then return ngx.exit(400) end

local ts  = tostring(ngx.time())
local mac = hmac:new(key, hmac.ALGOS.SHA256)
local sig = str.to_hex(mac:final(ref.."."..ts))

ngx.header["Set-Cookie"] =
    ("supabase_project=%s.%s.%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400")
    :format(ref, ts, sig)

ngx.say("ok")
