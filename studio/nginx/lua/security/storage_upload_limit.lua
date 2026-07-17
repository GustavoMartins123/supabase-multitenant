local cjson = require("cjson.safe")
local hmac_sha256 = require("security.hmac_sha256")
local secure_compare = require("security.secure_compare")

local _M = {}

local key = os.getenv("NGINX_HMAC_SECRET") or ""
local max_age = 604800

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

local function storage_limit_for_project(project_ref)
    local cookie = ngx.var.cookie_supabase_storage_limit
    if not cookie then
        return nil, "Limite de upload do projeto ausente"
    end
    if key == "" then
        return nil, "Chave de validacao do limite de upload ausente"
    end

    local ref, limit, ts, sig = cookie:match("^([^%.]+)%.(%d+)%.(%d+)%.([0-9a-f]+)$")
    if not ref or ref ~= project_ref then
        return nil, "Limite de upload nao corresponde ao projeto atual"
    end

    local age = ngx.time() - tonumber(ts)
    if age > max_age then
        return nil, "Limite de upload expirado"
    end

    local expected, err = hmac_sha256.hex(key, ref.."."..limit.."."..ts)
    if not expected then
        ngx.log(ngx.ERR, "Falha ao validar cookie de limite de storage: ", err)
        return nil, "Falha ao validar limite de upload"
    end

    if not secure_compare.equals(expected, sig) then
        return nil, "Assinatura do limite de upload invalida"
    end

    return parse_positive_integer(limit)
end

function _M.enforce()
    local method = ngx.req.get_method()
    if method ~= "POST" and method ~= "PUT" and method ~= "PATCH" then
        return
    end

    local uri = ngx.var.uri or ""
    if not is_upload_route(uri) then
        return
    end

    local project_ref = ngx.var.project_ref
    if not project_ref or project_ref == "" or project_ref == "default" then
        return
    end

    local request_size = request_upload_size()
    if not request_size then
        return
    end

    local limit, err = storage_limit_for_project(project_ref)
    if not limit then
        return reject(ngx.HTTP_FORBIDDEN, err, { error = "storage_limit_missing" })
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
