local cookie = ngx.var.cookie_supabase_project
if not cookie then
    return ""
end

local function expired_cookie_header()
    return "supabase_project=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
end

local ref, ts, sig = cookie:match("^([^%.]+)%.(%d+)%.([0-9a-f]+)$")
if not ref then
    return expired_cookie_header()
end

local ts_number = tonumber(ts)
if not ts_number then
    return expired_cookie_header()
end

local max_age = 604800
if ngx.time() - ts_number > max_age then
    return expired_cookie_header()
end

local hmac_sha256 = require("security.hmac_sha256")
local secure_compare = require("security.secure_compare")
local expect = hmac_sha256.hex(COOKIE_SECRET, ref .. "." .. ts)
if not expect or not secure_compare.equals(expect, sig) then
    return expired_cookie_header()
end

return ""
