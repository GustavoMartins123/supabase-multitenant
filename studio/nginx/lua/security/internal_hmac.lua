local digest = require("resty.openssl.digest")
local hmac_sha256 = require("security.hmac_sha256")
local random = require("resty.random")
local secure_compare = require("security.secure_compare")
local str = require("resty.string")

local M = {}
M.VERSION = "internal-hmac-v1"

local function get_header(headers, name)
    return headers[name] or headers[name:lower()]
end

function M.read_current_body()
    ngx.req.read_body()
    local body = ngx.req.get_body_data()
    if body then return body end
    local body_file = ngx.req.get_body_file()
    if not body_file then return "" end
    local file, err = io.open(body_file, "rb")
    if not file then return nil, err or "failed to open temporary request body" end
    local data = file:read("*a")
    file:close()
    return data or ""
end

function M.sha256_hex(value)
    local ctx, err = digest.new("sha256")
    if not ctx then return nil, err end
    local ok, update_err = ctx:update(value)
    if not ok then return nil, update_err end
    local raw, final_err = ctx:final()
    if not raw then return nil, final_err end
    return str.to_hex(raw)
end

function M.canonical(service, method, target, timestamp, nonce, body_hash)
    return table.concat({
        M.VERSION,
        service,
        string.upper(method),
        target,
        tostring(timestamp),
        nonce,
        body_hash,
    }, "\n")
end

local function new_nonce()
    local raw, err = random.bytes(16, true)
    if not raw then return nil, err or "failed to generate nonce" end
    return str.to_hex(raw)
end

function M.sign_headers(secret, service, method, target, body, timestamp, nonce)
    if not secret or secret == "" then return nil, "internal HMAC secret is missing" end
    if not service or service == "" then return nil, "internal service is missing" end
    timestamp = timestamp or ngx.time()
    if not nonce then
        local nonce_err
        nonce, nonce_err = new_nonce()
        if not nonce then return nil, nonce_err end
    end
    local body_hash, hash_err = M.sha256_hex(body or "")
    if not body_hash then return nil, hash_err end
    local canonical = M.canonical(service, method, target, timestamp, nonce, body_hash)
    local signature, sign_err = hmac_sha256.hex(secret, canonical)
    if not signature then return nil, sign_err end
    return {
        ["X-Internal-Version"] = M.VERSION,
        ["X-Internal-Service"] = service,
        -- Compatibilidade com locations antigas que zeram X-Internal-Service.
        -- O valor continua protegido porque a identidade entra no canonical HMAC.
        ["X-Internal-Caller"] = service,
        ["X-Internal-Timestamp"] = tostring(timestamp),
        ["X-Internal-Nonce"] = nonce,
        ["X-Internal-Signature"] = signature,
    }
end

function M.apply_current_request(secret, service, target)
    local body, body_err = M.read_current_body()
    if body == nil then return nil, body_err end
    local headers, sign_err = M.sign_headers(secret, service, ngx.req.get_method(), target, body)
    if not headers then return nil, sign_err end
    for name, value in pairs(headers) do ngx.req.set_header(name, value) end
    return true
end

function M.verify_current_request(secret, expected_service, options)
    options = options or {}
    local max_skew = tonumber(options.max_skew) or 60
    local nonce_cache = options.nonce_cache or ngx.shared.internal_hmac_nonces
    if not secret or secret == "" then
        return nil, ngx.HTTP_INTERNAL_SERVER_ERROR, "internal HMAC secret is missing"
    end
    local headers = ngx.req.get_headers()
    local version = get_header(headers, "X-Internal-Version") or ""
    local service = get_header(headers, "X-Internal-Service")
        or get_header(headers, "X-Internal-Caller")
        or ""
    local timestamp = tonumber(get_header(headers, "X-Internal-Timestamp") or "")
    local nonce = get_header(headers, "X-Internal-Nonce") or ""
    local provided_signature = get_header(headers, "X-Internal-Signature") or ""
    if version ~= M.VERSION then return nil, ngx.HTTP_UNAUTHORIZED, "Unsupported internal HMAC version" end
    if service ~= expected_service then return nil, ngx.HTTP_UNAUTHORIZED, "Invalid internal service" end
    if not timestamp or nonce == "" or provided_signature == "" then
        return nil, ngx.HTTP_UNAUTHORIZED, "Missing internal signature"
    end
    if not nonce:match("^[0-9a-fA-F]+$") or #nonce < 32 or #nonce > 128 then
        return nil, ngx.HTTP_UNAUTHORIZED, "Invalid internal nonce"
    end
    if not provided_signature:match("^[0-9a-fA-F]+$") or #provided_signature ~= 64 then
        return nil, ngx.HTTP_UNAUTHORIZED, "Invalid internal signature"
    end
    if math.abs(ngx.time() - timestamp) > max_skew then
        return nil, ngx.HTTP_UNAUTHORIZED, "Expired internal signature"
    end
    local body, body_err = M.read_current_body()
    if body == nil then return nil, ngx.HTTP_BAD_REQUEST, body_err or "Invalid request body" end
    local body_hash, hash_err = M.sha256_hex(body)
    if not body_hash then return nil, ngx.HTTP_INTERNAL_SERVER_ERROR, hash_err or "Failed to hash body" end
    local canonical = M.canonical(service, ngx.req.get_method(), ngx.var.request_uri, timestamp, nonce, body_hash)
    local expected_signature, sign_err = hmac_sha256.hex(secret, canonical)
    if not expected_signature then
        return nil, ngx.HTTP_INTERNAL_SERVER_ERROR, sign_err or "Failed to sign request"
    end
    if not secure_compare.equals(provided_signature, expected_signature) then
        return nil, ngx.HTTP_FORBIDDEN, "Invalid internal signature"
    end
    if not nonce_cache then
        return nil, ngx.HTTP_INTERNAL_SERVER_ERROR, "Internal nonce cache is unavailable"
    end
    local nonce_key = service .. ":" .. string.lower(nonce)
    local nonce_ttl = math.max(5, max_skew * 2 + 5)
    local added = nonce_cache:add(nonce_key, true, nonce_ttl)
    if not added then return nil, ngx.HTTP_UNAUTHORIZED, "Replayed internal signature" end
    return true
end

return M
