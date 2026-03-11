local cookie = ngx.var.cookie_supabase_project
if not cookie then return "default" end

local str     = require "resty.string"
local hmac    = require "resty.hmac"
local key     = COOKIE_SECRET

local ref, ts, sig = cookie:match("^([^%.]+)%.(%d+)%.([0-9a-f]+)$")
if not ref then return "default" end
if (ngx.time() - tonumber(ts)) > 86400 then   -- expirou
    return "default"
end
local mac = hmac:new(key, hmac.ALGOS.SHA256)
local expect = str.to_hex( mac:final(ref.."."..ts) )
if string.lower(expect) ~= string.lower(sig) then
    ngx.log(ngx.ERR, "Assinatura de cookie inválida para projeto: ", ref)
    return ngx.exit(403)
end
return ref
