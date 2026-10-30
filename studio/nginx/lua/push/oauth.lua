-- Shared Firebase identity; no tenant-specific Firebase credentials.
local cjson = require("cjson.safe")
local http = require("resty.http")
local lock = require("resty.lock")
local pkey = require("resty.openssl.pkey")
local digest = require("resty.openssl.digest")
local sha256 = require("resty.sha256")
local str = require("resty.string")
local outbound_tls = require("utils.outbound_tls")
local M = {}

function M.hash(value)
    local ctx = sha256:new()
    ctx:update(value)
    return str.to_hex(ctx:final())
end

function M.timeout(name, default)
    local value = tonumber(os.getenv(name)) or default
    if value <= 0 or value > 60000 then return default end
    return value
end

function M.client()
    local client = http.new()
    client:set_timeouts(M.timeout("PUSH_HTTP_CONNECT_TIMEOUT_MS", 5000),
                        M.timeout("PUSH_HTTP_SEND_TIMEOUT_MS", 10000),
                        M.timeout("PUSH_HTTP_READ_TIMEOUT_MS", 10000))
    return client
end

function M.lock_expiry(multiplier)
    return multiplier * (M.timeout("PUSH_HTTP_CONNECT_TIMEOUT_MS", 5000)
        + M.timeout("PUSH_HTTP_SEND_TIMEOUT_MS", 10000)
        + M.timeout("PUSH_HTTP_READ_TIMEOUT_MS", 10000)) / 1000 + 10
end

function M.identity(sa)
    -- Includes key material fingerprint to separate identities/key rotation;
    -- only the opaque hash is used in shared dictionary keys.
    return M.hash(sa.client_email .. "\0" .. sa.project_id .. "\0" .. sa.private_key)
end

local function b64url(value)
    return (ngx.encode_base64(value):gsub("+", "-"):gsub("/", "_"):gsub("=", ""))
end

local function refresh(sa)
    local now = ngx.time()
    local assertion = b64url(cjson.encode({alg="RS256", typ="JWT"})) .. "." .. b64url(cjson.encode({
        iss=sa.client_email, scope="https://www.googleapis.com/auth/firebase.messaging",
        aud="https://oauth2.googleapis.com/token", exp=now+3600, iat=now,
    }))
    local pk = pkey.new(sa.private_key)
    local ctx = digest.new("sha256")
    if not pk or not ctx or not ctx:update(assertion) then return nil, "AUTH_ERROR", 60 end
    local signature = pk:sign(ctx)
    if not signature then return nil, "AUTH_ERROR", 60 end
    local token_url = "https://oauth2.googleapis.com/token"
    local res = M.client():request_uri(token_url, outbound_tls.apply_public(token_url, {
        method="POST", body="grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion="
            .. assertion .. "." .. b64url(signature),
        headers={["Content-Type"]="application/x-www-form-urlencoded"},
    }))
    if not res then return nil, "TEMPORARY_FAILURE", 5 end
    if res.status ~= 200 then
        if res.status == 429 or res.status >= 500 then return nil, "TEMPORARY_FAILURE", 60 end
        return nil, "AUTH_ERROR", 60
    end
    local data = cjson.decode(res.body)
    local expires = type(data)=="table" and tonumber(data.expires_in)
    if not expires or expires <= 0 or expires > 86400 or type(data.access_token) ~= "string"
        or data.access_token == "" then return nil, "AUTH_ERROR", 60 end
    local margin = math.min(60, expires * 0.1)
    return data.access_token, nil, expires-margin
end

function M.get(sa)
    local cache = ngx.shared.push_oauth_tokens
    if not cache or not ngx.shared.push_locks then return nil, "AUTH_ERROR", 60 end
    local key = "oauth:" .. M.identity(sa)
    local token = cache:get(key)
    if token then return token end
    local failed = cache:get(key .. ":failure")
    if failed then return nil, failed, 60 end
    local mutex = lock:new("push_locks", {timeout=5, exptime=M.lock_expiry(1)})
    if not mutex then return nil, "TEMPORARY_FAILURE", 5 end
    local acquired = mutex:lock(key)
    if not acquired then return nil, "TEMPORARY_FAILURE", 5 end
    -- Every path, including exceptions, releases the lock; expiry is a final
    -- fallback if the nginx worker dies during an external call.
    local ok, value, category, ttl = pcall(function()
        local existing = cache:get(key)
        if existing then return existing end
        local failure = cache:get(key .. ":failure")
        if failure then return nil, failure, 60 end
        local access, err, lifetime = refresh(sa)
        if access then
            local stored = cache:safe_set(key, access, lifetime)
            if not stored then return nil, "TEMPORARY_FAILURE", 5 end
            return access
        end
        cache:safe_set(key .. ":failure", err, lifetime)
        return nil, err, lifetime
    end)
    mutex:unlock()
    if not ok then
        cache:safe_set(key .. ":failure", "AUTH_ERROR", 60)
        ngx.log(ngx.ERR, "[PUSH] OAuth refresh failed")
        return nil, "AUTH_ERROR", 60
    end
    return value, category, ttl
end

function M.invalidate(sa, rejected)
    local cache = ngx.shared.push_oauth_tokens
    local key = "oauth:" .. M.identity(sa)
    -- Use the same lock as refresh; a get/delete pair alone is not atomic
    -- across nginx workers. Cooldown also bounds repeated FCM auth failures.
    local mutex = lock:new("push_locks", {timeout=5, exptime=M.lock_expiry(1)})
    if not mutex or not mutex:lock(key) then return end
    if cache:get(key) == rejected then
        cache:delete(key)
        cache:safe_set(key .. ":failure", "AUTH_ERROR", 60)
    end
    mutex:unlock()
end

return M
