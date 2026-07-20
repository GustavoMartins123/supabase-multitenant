local cjson = require("cjson.safe")
local http = require("resty.http")

local _M = {}

local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local server_hostname = string.match(server_domain, "//([^/:]+)") or "localhost"
local shared_token = os.getenv("NGINX_SHARED_TOKEN") or ""
local verify_tls = (os.getenv("SERVICE_KEY_VERIFY_TLS") or "true"):lower() ~= "false"
local cache_ttl = tonumber(os.getenv("STUDIO_CONTEXT_CACHE_TTL_SECONDS")) or 5
local cache = ngx.shared.service_keys

cache_ttl = math.max(1, math.min(cache_ttl, 30))

local function cache_key(ref, user_id)
    return "studio-context:" .. user_id .. ":" .. ref
end

local function validate_context(context, ref)
    if type(context) ~= "table" or context.ref ~= ref then
        return nil, "invalid Studio context response"
    end
    if type(context.anon_key) ~= "string" or context.anon_key == "" then
        return nil, "Studio context has no anon key"
    end
    if type(context.project_uuid) ~= "string" or context.project_uuid == "" then
        return nil, "Studio context has no project UUID"
    end
    return context
end

function _M.load(ref)
    local user_id = ngx.var.auth_user_id or ""
    local user_token = ngx.var.auth_user_token or ""
    if user_id == "" or user_token == "" then
        return nil, "authenticated user context unavailable", ngx.HTTP_UNAUTHORIZED
    end
    if server_domain == "" or shared_token == "" then
        return nil, "Studio context service is not configured", ngx.HTTP_INTERNAL_SERVER_ERROR
    end

    local key = cache_key(ref, user_id)
    if cache then
        local cached = cache:get(key)
        if cached then
            local decoded = cjson.decode(cached)
            local context = validate_context(decoded, ref)
            if context then
                return context
            end
            cache:delete(key)
        end
    end

    local httpc = http.new()
    httpc:set_timeout(2000)
    local response, request_err = httpc:request_uri(
        server_domain .. "/api/projects/internal/studio-context/" .. ref,
        {
            method = "GET",
            headers = {
                ["Accept"] = "application/json",
                ["Host"] = server_hostname,
                ["X-Internal-Service"] = "studio-nginx",
                ["X-Shared-Token"] = shared_token,
                ["X-User-Token"] = user_token,
            },
            ssl_verify = verify_tls,
            ssl_server_name = server_hostname,
            keepalive = true,
        }
    )

    if not response then
        ngx.log(
            ngx.ERR,
            "Studio context service request failed: ",
            request_err or "unknown error"
        )
        return nil, "Studio context service unavailable", ngx.HTTP_SERVICE_UNAVAILABLE
    end
    if response.status < 200 or response.status >= 300 then
        if response.status == ngx.HTTP_FORBIDDEN
            or response.status == ngx.HTTP_NOT_FOUND
        then
            return nil, "Project not found", ngx.HTTP_NOT_FOUND
        end
        if response.status >= 500 then
            ngx.log(
                ngx.ERR,
                "Studio context service returned status ",
                response.status
            )
            return nil, "Studio context service unavailable", ngx.HTTP_SERVICE_UNAVAILABLE
        end
        local problem = cjson.decode(response.body or "") or {}
        return nil, problem.detail or "Project context unavailable", response.status
    end

    local decoded, decode_err = cjson.decode(response.body or "")
    local context, validation_err = validate_context(decoded, ref)
    if not context then
        ngx.log(
            ngx.ERR,
            "Invalid Studio context response: ",
            validation_err or decode_err or "unknown error"
        )
        return nil, "Invalid response from Studio context service", ngx.HTTP_SERVICE_UNAVAILABLE
    end

    if cache then
        local encoded = cjson.encode(context)
        if encoded then
            cache:set(key, encoded, cache_ttl)
        end
    end
    return context
end

return _M
