local cookie = ngx.var.cookie_supabase_project
if not cookie then return "default" end

local str     = require "resty.string"
local hmac    = require "resty.hmac"
local key     = COOKIE_SECRET

local ref, ts, sig = cookie:match("^([^%.]+)%.(%d+)%.([0-9a-f]+)$")
if not ref then return "default" end

local cookie_age = ngx.time() - tonumber(ts)
local max_age = 604800

if cookie_age > max_age then
    return "default"
end

local mac = hmac:new(key, hmac.ALGOS.SHA256)
local expect = str.to_hex(mac:final(ref.."."..ts))
if string.lower(expect) ~= string.lower(sig) then
    ngx.log(ngx.ERR, "Assinatura de cookie inválida para projeto: ", ref)
    return "default"
end

local renewal_threshold = 518400

if cookie_age > renewal_threshold then
    local new_ts = tostring(ngx.time())
    local new_mac = hmac:new(key, hmac.ALGOS.SHA256)
    local new_sig = str.to_hex(new_mac:final(ref.."."..new_ts))
    
    ngx.header["Set-Cookie"] = 
        ("supabase_project=%s.%s.%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d")
        :format(ref, new_ts, new_sig, max_age)
    
    ngx.log(ngx.INFO, "[COOKIE_RENEWAL] Cookie renovado para projeto: ", ref, 
            " (idade anterior: ", cookie_age, "s)")
end

return ref
