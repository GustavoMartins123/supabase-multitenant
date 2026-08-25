local cjson = require("cjson.safe")
local http = require("resty.http")
local pkey = require("resty.openssl.pkey")
local digest = require("resty.openssl.digest")
local outbound_tls = require("utils.outbound_tls")

local function respond(status, payload)
    ngx.status = status
    ngx.header.content_type = "application/json"
    ngx.say(payload)
end

local function b64url(value)
    local encoded = ngx.encode_base64(value)
    return encoded:gsub("+", "-"):gsub("/", "_"):gsub("=", "")
end

local function env_number(name, default)
    return tonumber(os.getenv(name) or tostring(default)) or default
end

local function read_json_body()
    ngx.req.read_body()
    local raw = ngx.req.get_body_data()
    if not raw then
        return nil, "request body is unavailable"
    end

    local value, err = cjson.decode(raw)
    if not value then
        return nil, err or "invalid JSON"
    end
    return value
end

local req_body, body_err = read_json_body()
if not req_body or not req_body.token or not req_body.body then
    respond(400, cjson.encode({error = "Invalid payload", detail = body_err}))
    return
end

local delivery_key = tostring(req_body.idempotency_key or "")
if not delivery_key:match("^[%w_%-]+$") or #delivery_key > 128 then
    respond(400, cjson.encode({error = "Invalid idempotency key"}))
    return
end

local idempotency_cache = ngx.shared.push_idempotency
local cached = idempotency_cache and idempotency_cache:get(delivery_key)
if cached then
    local cached_response = cjson.decode(cached)
    if cached_response and cached_response.status and cached_response.body then
        ngx.status = tonumber(cached_response.status) or 200
        ngx.header.content_type = "application/json"
        ngx.say(cached_response.body)
        return
    end
end

local sa_file = io.open("/config/firebase.json", "r")
if not sa_file then
    respond(500, cjson.encode({error = "firebase.json not found"}))
    return
end

local sa_data, sa_err = cjson.decode(sa_file:read("*a"))
sa_file:close()
if not sa_data or not sa_data.client_email or not sa_data.private_key or not sa_data.project_id then
    respond(500, cjson.encode({error = "Invalid Firebase service account", detail = sa_err}))
    return
end

local function get_access_token()
    local oauth_cache = ngx.shared.push_oauth_tokens
    local cache_key = "oauth:" .. sa_data.client_email
    if oauth_cache then
        local cached_token = oauth_cache:get(cache_key)
        if cached_token then
            local token_data = cjson.decode(cached_token)
            if token_data and token_data.access_token and tonumber(token_data.expires_at or 0) > ngx.time() + 60 then
                return token_data.access_token
            end
        end
    end

    local header = b64url(cjson.encode({alg = "RS256", typ = "JWT"}))
    local now = ngx.time()
    local claim = b64url(cjson.encode({
        iss = sa_data.client_email,
        scope = "https://www.googleapis.com/auth/firebase.messaging",
        aud = "https://oauth2.googleapis.com/token",
        exp = now + 3600,
        iat = now,
    }))

    local to_sign = header .. "." .. claim
    local pk, key_err = pkey.new(sa_data.private_key)
    if not pk then
        return nil, "Invalid private key: " .. tostring(key_err)
    end

    local digest_ctx, digest_err = digest.new("sha256")
    if not digest_ctx then
        return nil, "Cannot initialize digest: " .. tostring(digest_err)
    end
    local updated, update_err = digest_ctx:update(to_sign)
    if not updated then
        return nil, "Cannot update digest: " .. tostring(update_err)
    end
    local signature, sign_err = pk:sign(digest_ctx)
    if not signature then
        return nil, "Cannot sign OAuth assertion: " .. tostring(sign_err)
    end

    local jwt = to_sign .. "." .. b64url(signature)
    local httpc = http.new()
    httpc:set_timeouts(
        env_number("PUSH_HTTP_CONNECT_TIMEOUT_MS", 5000),
        env_number("PUSH_HTTP_SEND_TIMEOUT_MS", 10000),
        env_number("PUSH_HTTP_READ_TIMEOUT_MS", 10000)
    )
    local token_url = "https://oauth2.googleapis.com/token"
    local token_res, token_err = httpc:request_uri(token_url, outbound_tls.apply_public(token_url, {
        method = "POST",
        body = "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" .. jwt,
        headers = { ["Content-Type"] = "application/x-www-form-urlencoded" },
    }))
    if not token_res or token_res.status ~= 200 then
        return nil, token_res and token_res.body or token_err or "OAuth request failed"
    end

    local token_data, decode_err = cjson.decode(token_res.body)
    if not token_data or not token_data.access_token then
        return nil, decode_err or "OAuth response did not contain access_token"
    end

    local expires_in = tonumber(token_data.expires_in or 3600) or 3600
    if oauth_cache then
        oauth_cache:set(cache_key, cjson.encode({
            access_token = token_data.access_token,
            expires_at = ngx.time() + expires_in,
        }), math.max(60, expires_in - 60))
    end
    return token_data.access_token
end

local access_token, access_token_err = get_access_token()
if not access_token then
    respond(502, cjson.encode({error = "Failed to get access token", detail = access_token_err}))
    return
end

local fcm_payload = cjson.encode({
    message = {
        token = req_body.token,
        notification = {
            title = "Nova Notificação",
            body = req_body.body,
        },
    },
})

local fcm_url = "https://fcm.googleapis.com/v1/projects/" .. sa_data.project_id .. "/messages:send"
local httpc = http.new()
httpc:set_timeouts(
    env_number("PUSH_HTTP_CONNECT_TIMEOUT_MS", 5000),
    env_number("PUSH_HTTP_SEND_TIMEOUT_MS", 10000),
    env_number("PUSH_HTTP_READ_TIMEOUT_MS", 10000)
)
local fcm_res, fcm_err = httpc:request_uri(fcm_url, outbound_tls.apply_public(fcm_url, {
    method = "POST",
    body = fcm_payload,
    headers = {
        ["Authorization"] = "Bearer " .. access_token,
        ["Content-Type"] = "application/json",
    },
}))

local status = fcm_res and fcm_res.status or 502
local response_body = fcm_res and fcm_res.body or cjson.encode({error = fcm_err or "FCM request failed"})
if status >= 200 and status < 300 and idempotency_cache then
    local ttl = env_number("PUSH_IDEMPOTENCY_TTL_SECONDS", 86400)
    if ttl > 0 then
        idempotency_cache:set(
            delivery_key,
            cjson.encode({status = status, body = response_body}),
            ttl
        )
    end
end

respond(status, response_body)
