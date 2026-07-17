local digest = require("resty.openssl.digest")
local hmac_sha256 = require("security.hmac_sha256")
local secure_compare = require("security.secure_compare")
local str = require("resty.string")

local secret = os.getenv("INTERNAL_HMAC_SECRET") or ""
local max_skew = tonumber(os.getenv("INTERNAL_HMAC_MAX_SKEW_SECONDS") or "60") or 60

local function respond(status, message)
    ngx.status = status
    ngx.header.content_type = "application/json"
    ngx.say('{"error":"' .. message .. '"}')
    return ngx.exit(status)
end

local function get_header(headers, name)
    return headers[name] or headers[name:lower()]
end

local function read_body()
    ngx.req.read_body()

    local body = ngx.req.get_body_data()
    if body then
        return body
    end

    local body_file = ngx.req.get_body_file()
    if not body_file then
        return ""
    end

    local file, err = io.open(body_file, "rb")
    if not file then
        ngx.log(ngx.ERR, "[PUSH] Falha ao ler body temporario: ", err or "erro desconhecido")
        return nil
    end

    local data = file:read("*a")
    file:close()
    return data or ""
end

local function sha256_hex(value)
    local ctx, err = digest.new("sha256")
    if not ctx then
        return nil, err
    end

    local ok, update_err = ctx:update(value)
    if not ok then
        return nil, update_err
    end

    local raw, final_err = ctx:final()
    if not raw then
        return nil, final_err
    end

    return str.to_hex(raw)
end

if ngx.var.request_method ~= "POST" then
    return respond(ngx.HTTP_METHOD_NOT_ALLOWED, "Use POST method")
end

if secret == "" then
    ngx.log(ngx.ERR, "[PUSH] INTERNAL_HMAC_SECRET nao configurado")
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local headers = ngx.req.get_headers()
local service = get_header(headers, "X-Internal-Service")
local timestamp = tonumber(get_header(headers, "X-Internal-Timestamp") or "")
local nonce = get_header(headers, "X-Internal-Nonce")
local provided_signature = get_header(headers, "X-Internal-Signature")

if service ~= "push-worker" then
    ngx.log(ngx.WARN, "[PUSH] Servico interno invalido: ", service or "")
    return respond(ngx.HTTP_UNAUTHORIZED, "Invalid internal service")
end

if not timestamp or not nonce or nonce == "" or not provided_signature or provided_signature == "" then
    ngx.log(ngx.WARN, "[PUSH] Headers HMAC ausentes")
    return respond(ngx.HTTP_UNAUTHORIZED, "Missing internal signature")
end

local now = ngx.time()
if math.abs(now - timestamp) > max_skew then
    ngx.log(ngx.WARN, "[PUSH] Timestamp HMAC fora da janela: ", timestamp)
    return respond(ngx.HTTP_UNAUTHORIZED, "Expired internal signature")
end

local nonce_cache = ngx.shared.internal_hmac_nonces
if not nonce_cache then
    ngx.log(ngx.ERR, "[PUSH] lua_shared_dict internal_hmac_nonces nao configurado")
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local body = read_body()
if body == nil then
    return respond(ngx.HTTP_BAD_REQUEST, "Invalid request body")
end

local body_hash, hash_err = sha256_hex(body)
if not body_hash then
    ngx.log(ngx.ERR, "[PUSH] Falha ao calcular sha256 do body: ", hash_err or "erro desconhecido")
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local canonical = table.concat({
    "push-v2",
    ngx.var.request_method,
    ngx.var.request_uri,
    tostring(timestamp),
    nonce,
    body_hash,
}, "\n")

local expected_signature, sign_err = hmac_sha256.hex(secret, canonical)
if not expected_signature then
    ngx.log(ngx.ERR, "[PUSH] Falha ao calcular HMAC: ", sign_err or "erro desconhecido")
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

if not secure_compare.equals(provided_signature, expected_signature) then
    ngx.log(ngx.WARN, "[PUSH] Assinatura HMAC invalida para /api/internal/push")
    return respond(ngx.HTTP_FORBIDDEN, "Invalid internal signature")
end

local nonce_key = service .. ":" .. nonce
local nonce_added, nonce_err = nonce_cache:add(nonce_key, true, max_skew)
if not nonce_added then
    ngx.log(ngx.WARN, "[PUSH] Nonce HMAC reutilizado ou invalido: ", nonce_err or "exists")
    return respond(ngx.HTTP_UNAUTHORIZED, "Replayed internal signature")
end
