local cjson = require("cjson.safe")
local http = require("resty.http")
local internal_hmac = require("security.internal_hmac")
local outbound_tls = require("utils.outbound_tls")

local _M = {}

local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local server_hostname = string.match(server_domain, "//([^/:]+)")
local service_hmac_secret = os.getenv("STUDIO_GATEWAY_HMAC_SECRET") or ""

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

function _M.load(ref, administrative)
    local user_id = ngx.var.auth_user_id or ""
    local user_token = ngx.var.auth_user_token or ""
    if user_id == "" or user_token == "" then
        return nil, "authenticated user context unavailable", ngx.HTTP_UNAUTHORIZED
    end
    if not server_hostname or service_hmac_secret == "" then
        return nil, "Studio context service is not configured", ngx.HTTP_INTERNAL_SERVER_ERROR
    end

    local target = "/api/projects/internal/studio-context/" .. ref
    if administrative then
        target = target .. "?access=admin"
    end
    local signed_headers, sign_err = internal_hmac.sign_headers(
        service_hmac_secret,
        "studio-nginx",
        "GET",
        target,
        ""
    )
    if not signed_headers then
        return nil, sign_err or "failed to sign Studio context request", ngx.HTTP_INTERNAL_SERVER_ERROR
    end
    signed_headers["Accept"] = "application/json"
    signed_headers["Host"] = server_hostname
    signed_headers["X-User-Token"] = user_token

    local httpc = http.new()
    httpc:set_timeout(2000)
    local response, request_err = httpc:request_uri(
        server_domain .. target,
        outbound_tls.apply_internal(server_domain .. target, {
            method = "GET",
            headers = signed_headers,
            keepalive = true,
        })
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

    return context
end

return _M
