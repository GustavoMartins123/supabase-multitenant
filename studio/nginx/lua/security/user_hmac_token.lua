local cjson = require("cjson.safe")
local hmac_sha256 = require("security.hmac_sha256")

local M = {}

local SECRET = os.getenv("NGINX_HMAC_SECRET") or ""
local TTL_SECONDS = tonumber(os.getenv("NGINX_HMAC_TOKEN_TTL") or "300") or 300

local AUDIENCE = "projects-api"

local function base64url_encode(value)
    return ngx.encode_base64(value):gsub("%+", "-"):gsub("/", "_"):gsub("=+$", "")
end

function M.new_jti()
    local raw = require("resty.random").bytes(16, true)
    if not raw then
        return nil, "fonte de entropia indisponivel"
    end
    return base64url_encode(raw)
end

function M.sign(user_id, extra_claims)
    if not user_id or user_id == "" then
        return nil, "user_id ausente"
    end
    if SECRET == "" then
        return nil, "NGINX_HMAC_SECRET ausente"
    end

    local jti, jti_err = M.new_jti()
    if not jti then
        return nil, jti_err or "falha ao gerar jti"
    end

    local now = ngx.time()
    local claims = {
        sub = tostring(user_id),
        aud = AUDIENCE,
        jti = jti,
        iat = now,
        exp = now + TTL_SECONDS,
    }

    if type(extra_claims) == "table" then
        for key, value in pairs(extra_claims) do
            if value ~= nil and value ~= "" then
                claims[key] = value
            end
        end
    end

    local payload = cjson.encode(claims)
    if not payload then
        return nil, "falha ao serializar claims"
    end

    local encoded_payload = base64url_encode(payload)
    local signature, err = hmac_sha256.hex(SECRET, encoded_payload)
    if not signature then
        return nil, err or "falha ao assinar token"
    end

    return "v1." .. encoded_payload .. "." .. signature, nil
end


M.AUDIENCE = AUDIENCE

return M
