local hmac_sha256 = require "utils.hmac_sha256"
local key = COOKIE_SECRET
local ref = ngx.var.arg_ref
if not ref or ref == "" then return ngx.exit(400) end

local ts  = tostring(ngx.time())
local sig, err = hmac_sha256.hex(key, ref.."."..ts)
if not sig then
    ngx.log(ngx.ERR, "Falha ao assinar cookie de projeto: ", err)
    return ngx.exit(500)
end

ngx.header["Set-Cookie"] =
    ("supabase_project=%s.%s.%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800")
    :format(ref, ts, sig)

ngx.say("ok")
