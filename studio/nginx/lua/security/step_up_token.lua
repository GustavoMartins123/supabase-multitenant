local cjson = require("cjson.safe")
local random = require("resty.random")
local hmac_sha256 = require("security.hmac_sha256")

local M = { TTL_SECONDS = 300 }

local SECRET = os.getenv("NGINX_HMAC_SECRET") or ""
local KEY_CONTEXT = "supabase-multitenant:step-up-token:v1"

local function base64url_encode(value)
    return ngx.encode_base64(value):gsub("%+", "-"):gsub("/", "_"):gsub("=+$", "")
end

function M.sign(user_id, login_session, action, project, resource)
    if SECRET == "" then
        return nil, "NGINX_HMAC_SECRET ausente"
    end
    if not user_id or user_id == "" or not login_session or login_session == "" then
        return nil, "binding de usuario ou sessao ausente"
    end

    local signing_key, derive_err = hmac_sha256.raw(SECRET, KEY_CONTEXT)
    if not signing_key then
        return nil, derive_err or "falha ao derivar chave de step-up"
    end
    local nonce = random.bytes(16, true)
    if not nonce then
        return nil, "CSPRNG indisponivel"
    end

    local now = ngx.time()
    local payload, encode_err = cjson.encode({
        sub = tostring(user_id),
        iat = now,
        exp = now + M.TTL_SECONDS,
        login_session = login_session,
        action = action,
        project = project,
        resource = resource,
        jti = base64url_encode(nonce),
    })
    if not payload then
        return nil, encode_err or "falha ao serializar grant de step-up"
    end

    local encoded_payload = base64url_encode(payload)
    local signature, sign_err = hmac_sha256.hex(signing_key, encoded_payload)
    if not signature then
        return nil, sign_err or "falha ao assinar grant de step-up"
    end
    return "su1." .. encoded_payload .. "." .. signature, nil
end

return M
