local hmac_sha256 = require("security.hmac_sha256")
local secure_compare = require("security.secure_compare")
local key = COOKIE_SECRET
local storage_limit_key = os.getenv("NGINX_HMAC_SECRET") or ""
local ref = ngx.var.arg_ref
if not ref or ref == "" then return ngx.exit(400) end
local resolver = require("project_context.project_ref_resolver")
if not resolver.valid_ref(ref) then return ngx.exit(400) end

if resolver.is_slug_mode() then
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(([[{"mode":"slug","project_ref":"%s","path":"/project/%s"}]])
        :format(ref, ref))
    return
end

local storage_limit_token = ngx.var.arg_storage_limit_token

local ts  = tostring(ngx.time())
local sig, err = hmac_sha256.hex(key, ref.."."..ts)
if not sig then
    ngx.log(ngx.ERR, "Falha ao assinar cookie de projeto: ", err)
    return ngx.exit(500)
end

local cookies = {
    ("supabase_project=%s.%s.%s; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800")
        :format(ref, ts, sig)
}

if storage_limit_token and storage_limit_token ~= "" then
    local limit_ref, limit, limit_ts, limit_sig =
        storage_limit_token:match("^([^%.]+)%.(%d+)%.(%d+)%.([0-9a-f]+)$")

    if not limit_ref or limit_ref ~= ref or storage_limit_key == "" then
        return ngx.exit(400)
    end

    local expected, limit_err = hmac_sha256.hex(storage_limit_key, limit_ref.."."..limit.."."..limit_ts)
    if not expected then
        ngx.log(ngx.ERR, "Falha ao validar token de limite de storage: ", limit_err)
        return ngx.exit(500)
    end

    if not secure_compare.equals(expected, limit_sig) then
        return ngx.exit(400)
    end

    table.insert(
        cookies,
        ("supabase_storage_limit=%s; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800")
            :format(storage_limit_token)
    )
end

ngx.header["Set-Cookie"] = cookies

ngx.say("ok")
