local cjson = require("utils.json")
local internal_hmac = require("security.internal_hmac")

local _M = {}

local function reject(status, code, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json"
    ngx.say(cjson.encode({ error = code, message = message }))
    return ngx.exit(status)
end

function _M.handle(context)
    local route = ngx.ctx.storage_platform_local_response
    if type(route) ~= "table" or route.local_response ~= "object_public_url" then
        return
    end

    local raw_body, read_err = internal_hmac.read_current_body()
    if raw_body == nil then
        return reject(
            ngx.HTTP_BAD_REQUEST,
            "storage_platform_body_unreadable",
            read_err or "Nao foi possivel ler o corpo da requisicao"
        )
    end
    local body = cjson.decode(raw_body)
    if type(body) ~= "table" or type(body.path) ~= "string" or body.path == "" then
        return reject(
            ngx.HTTP_BAD_REQUEST,
            "storage_platform_object_path_missing",
            "path e obrigatorio para resolver a URL publica"
        )
    end

    local origin = ngx.var.studio_public_origin or ""
    if origin == "" or type(context) ~= "table" or not context.ref then
        return reject(
            ngx.HTTP_INTERNAL_SERVER_ERROR,
            "storage_platform_public_origin_missing",
            "Origem publica do Studio indisponivel"
        )
    end

    local object_path = ngx.re.gsub(body.path, "^/+", "", "jo")

    ngx.status = ngx.HTTP_OK
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(cjson.encode({
        publicUrl = origin
            .. "/storage/v1/"
            .. context.ref
            .. "/object/public/"
            .. route.bucket_id
            .. "/"
            .. object_path,
    }))
    return ngx.exit(ngx.HTTP_OK)
end

return _M
