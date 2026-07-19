local cjson = require("cjson.safe")
local _M = {}

local function parse_positive_integer(value)
    value = tostring(value or ""):match("^%s*(.-)%s*$")
    if value == "" or not value:match("^%d+$") then
        return nil
    end

    local parsed = tonumber(value)
    if not parsed or parsed < 1 then
        return nil
    end

    return parsed
end

local function request_upload_size()
    local headers = ngx.req.get_headers()
    local upload_length = parse_positive_integer(headers["Upload-Length"] or headers["upload-length"])
    local content_length = parse_positive_integer(headers["Content-Length"] or headers["content-length"])

    if upload_length and content_length then
        return math.max(upload_length, content_length)
    end

    return upload_length or content_length
end

local function is_upload_route(uri)
    if uri:find("^/storage/v1/upload/resumable") then
        return true
    end

    if uri:find("^/storage/v1/object/sign") then
        return false
    end
    if uri:find("^/storage/v1/object/list") then
        return false
    end
    if uri:find("^/storage/v1/object/move") then
        return false
    end

    if uri:find("^/storage/v1/object/") then
        return true
    end

    return false
end

local function reject(status, message, extra)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json"

    local payload = extra or {}
    payload.error = payload.error or message
    payload.message = message

    ngx.say(cjson.encode(payload))
    return ngx.exit(status)
end

function _M.enforce(context)
    local method = ngx.req.get_method()
    if method ~= "POST" and method ~= "PUT" and method ~= "PATCH" then
        return
    end

    local uri = ngx.var.uri or ""
    if not is_upload_route(uri) then
        return
    end

    if type(context) ~= "table" then
        return
    end

    local request_size = request_upload_size()
    if not request_size then
        return
    end

    local limit = parse_positive_integer(context.file_size_limit)
    if not limit then
        return reject(ngx.HTTP_FORBIDDEN, "Limite de upload do projeto ausente", {
            error = "storage_limit_missing",
        })
    end

    if request_size <= limit then
        return
    end

    return reject(ngx.HTTP_REQUEST_ENTITY_TOO_LARGE, "Upload excede o FILE_SIZE_LIMIT configurado para este projeto", {
        error = "payload_too_large",
        max_size = limit,
        received_size = request_size,
    })
end

return _M
