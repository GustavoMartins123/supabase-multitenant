local cookie = ngx.var.cookie_supabase_project
if not cookie then return "default" end

local function should_log_invalid_cookie()
    local uri = ngx.var.uri or ""
    return not (
        uri == "/auth"
        or uri:match("^/auth/")
        or uri == "/login"
        or uri == "/logout"
    )
end

local hmac_sha256 = require "utils.hmac_sha256"
local key = COOKIE_SECRET

local ref, ts, sig = cookie:match("^([^%.]+)%.(%d+)%.([0-9a-f]+)$")
if not ref then
    if should_log_invalid_cookie() then
        ngx.log(ngx.WARN, "Cookie de projeto malformado; limpando cookie")
    end
    return "default"
end

local cookie_age = ngx.time() - tonumber(ts)
local max_age = 604800

if cookie_age > max_age then
    if should_log_invalid_cookie() then
        ngx.log(ngx.INFO, "Cookie de projeto expirado para projeto: ", ref)
    end
    return "default"
end

local expect, err = hmac_sha256.hex(key, ref.."."..ts)
if not expect then
    ngx.log(ngx.ERR, "Falha ao validar cookie de projeto: ", err)
    return "default"
end
if string.lower(expect) ~= string.lower(sig) then
    if should_log_invalid_cookie() then
        ngx.log(ngx.WARN, "Assinatura de cookie inválida para projeto: ", ref, "; limpando cookie")
    end
    return "default"
end

local renewal_threshold = 518400

if cookie_age > renewal_threshold then
    local new_ts = tostring(ngx.time())
    local new_sig, renewal_err = hmac_sha256.hex(key, ref.."."..new_ts)
    if not new_sig then
        ngx.log(ngx.ERR, "Falha ao renovar cookie de projeto: ", renewal_err)
        return ref
    end

    ngx.header["Set-Cookie"] =
        ("supabase_project=%s.%s.%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d")
        :format(ref, new_ts, new_sig, max_age)

    ngx.log(ngx.INFO, "[COOKIE_RENEWAL] Cookie renovado para projeto: ", ref,
            " (idade anterior: ", cookie_age, "s)")
end

return ref
