local internal_hmac = require("security.internal_hmac")

local M = {}
local SECRET = os.getenv("STUDIO_ANALYTICS_HMAC_SECRET") or ""
local SERVICE = "studio-server"
local MAX_BODY_BYTES = 256 * 1024
local MAX_QUERY_BYTES = 16 * 1024
local MAX_HEADER_BYTES = 16 * 1024
local MAX_HEADERS = 64
local MAX_SKEW = tonumber(os.getenv("INTERNAL_HMAC_MAX_SKEW_SECONDS") or "60") or 60

local HTTP_LENGTH_REQUIRED = 411
local HTTP_REQUEST_ENTITY_TOO_LARGE = 413
local HTTP_REQUEST_URI_TOO_LARGE = 414
local HTTP_UNSUPPORTED_MEDIA_TYPE = 415
local HTTP_REQUEST_HEADER_FIELDS_TOO_LARGE = 431

local function header_value(headers, name)
    local value = headers[name] or headers[string.lower(name)]
    if type(value) == "table" then
        return value[1]
    end
    return value
end

local function error_result(status, code, message, allow)
    return nil, status, code, message, allow
end

local function allowed_methods(path)
    local endpoint = path:match("^api/endpoints/query/([%w._%-]+)$")
    if endpoint and #endpoint <= 128 then
        return { GET = true }, "GET"
    end
    if path == "api/backends" then
        return { GET = true, POST = true }, "GET, POST"
    end
    local backend_id = path:match("^api/backends/([%w_%-]+)$")
    if backend_id and #backend_id <= 128 then
        return { GET = true, PUT = true, DELETE = true }, "GET, PUT, DELETE"
    end
    if path == "api/sources" then
        return { GET = true }, "GET"
    end
    if path == "api/rules" then
        return { POST = true }, "POST"
    end
    return nil
end

local function header_size(headers)
    local total = 0
    for name, value in pairs(headers) do
        total = total + #tostring(name)
        if type(value) == "table" then
            for _, item in ipairs(value) do
                total = total + #tostring(item)
            end
        else
            total = total + #tostring(value)
        end
        if total > MAX_HEADER_BYTES then
            return total
        end
    end
    return total
end

function M.check()
    local uri = ngx.var.uri or ""
    local path = uri:match("^/_internal/logflare/(.+)$")
    if not path then
        return true
    end

    if #path > 256 or path:find("..", 1, true) then
        return error_result(ngx.HTTP_NOT_FOUND, "analytics_path_not_allowed", "Analytics path not allowed")
    end

    local methods, allow = allowed_methods(path)
    if not methods then
        return error_result(ngx.HTTP_NOT_FOUND, "analytics_path_not_allowed", "Analytics path not allowed")
    end

    local method = ngx.req.get_method()
    if not methods[method] then
        return error_result(ngx.HTTP_NOT_ALLOWED, "analytics_method_not_allowed", "Analytics method not allowed", allow)
    end

    local args = ngx.var.args or ""
    if #args > MAX_QUERY_BYTES then
        return error_result(HTTP_REQUEST_URI_TOO_LARGE, "analytics_query_too_large", "Analytics query is too large")
    end

    local headers, headers_err = ngx.req.get_headers(MAX_HEADERS, true)
    if headers_err == "truncated" or header_size(headers) > MAX_HEADER_BYTES then
        return error_result(HTTP_REQUEST_HEADER_FIELDS_TOO_LARGE, "analytics_headers_too_large", "Analytics request headers are too large")
    end

    local transfer_encoding = tostring(header_value(headers, "Transfer-Encoding") or "")
    if transfer_encoding ~= "" then
        return error_result(ngx.HTTP_BAD_REQUEST, "analytics_transfer_encoding_forbidden", "Transfer-Encoding is not allowed")
    end

    local raw_length = header_value(headers, "Content-Length")
    local content_length = raw_length and tonumber(raw_length) or nil
    if raw_length and (not content_length or content_length < 0 or content_length ~= math.floor(content_length)) then
        return error_result(ngx.HTTP_BAD_REQUEST, "analytics_invalid_content_length", "Invalid Content-Length")
    end

    if method == "POST" or method == "PUT" then
        if content_length == nil then
            return error_result(HTTP_LENGTH_REQUIRED, "analytics_content_length_required", "Content-Length is required")
        end
        if content_length > MAX_BODY_BYTES then
            return error_result(HTTP_REQUEST_ENTITY_TOO_LARGE, "analytics_body_too_large", "Analytics request body is too large")
        end
        local content_type = tostring(header_value(headers, "Content-Type") or ""):lower()
        if not content_type:match("^application/json%s*;?.*$") then
            return error_result(HTTP_UNSUPPORTED_MEDIA_TYPE, "analytics_content_type_not_allowed", "Analytics mutations require application/json")
        end
    elseif content_length and content_length > 0 then
        return error_result(ngx.HTTP_BAD_REQUEST, "analytics_body_not_allowed", "Request body is not allowed for this Analytics method")
    end

    local verified, verify_status, verify_err = internal_hmac.verify_current_request(
        SECRET,
        SERVICE,
        { max_skew = MAX_SKEW, nonce_cache = ngx.shared.internal_hmac_nonces }
    )
    if not verified then
        return error_result(
            verify_status or ngx.HTTP_UNAUTHORIZED,
            "analytics_internal_auth_failed",
            verify_err or "Internal Analytics authentication failed"
        )
    end

    for _, name in ipairs({
        "Authorization",
        "X-API-KEY",
        "Cookie",
        "Proxy-Authorization",
        "X-User-Token",
        "X-User-Groups",
        "X-User-Username",
        "X-User-Display-Name",
        "Remote-Groups",
        "X-Project-Ref",
    }) do
        ngx.req.clear_header(name)
    end

    return true
end

M.allowed_methods = allowed_methods
return M
