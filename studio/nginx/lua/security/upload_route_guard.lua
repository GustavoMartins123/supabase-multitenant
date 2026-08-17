local cjson = require("cjson.safe")
local projects_api_signer = require("security.projects_api_signer")

-- Compatibilidade do Studio: /object/sign e um alias local do endpoint real
-- do Storage. A antiga diretiva nginx usava $1 sem capture group; corrigimos
-- antes da selecao de location para cair diretamente em /storage/v1.
if (ngx.var.uri or "") == "/object/sign" then
    ngx.req.set_uri("/storage/v1/object/sign", true)
    return
end

local signed, sign_err = projects_api_signer.maybe_sign()
if not signed then
    ngx.log(ngx.ERR, "[INTERNAL-HMAC] Failed to sign Projects API request: ", sign_err or "unknown")
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.header["Content-Type"] = "application/json"
    ngx.say(cjson.encode({
        error = "internal_service_signing_failed",
        message = "Internal service authentication is unavailable",
    }))
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end

local method = ngx.req.get_method()
local uri = ngx.var.uri or ""

if method ~= "POST" and method ~= "PUT" and method ~= "PATCH" then
    return
end

if uri:find("^/storage/v1")
    or uri:find("^/api/platform/storage")
    or uri:find("^/api/user/me/avatar$")
then
    return
end

local headers = ngx.req.get_headers()
local content_type = tostring(
    headers["Content-Type"] or headers["content-type"] or ""
):lower()
local has_upload_length = headers["Upload-Length"] or headers["upload-length"]

local file_content_types = {
    "^multipart/form%-data",
    "^application/octet%-stream",
    "^application/pdf",
    "^application/zip",
    "^application/gzip",
    "^application/x%-7z%-compressed",
    "^application/x%-gzip",
    "^application/x%-rar%-compressed",
    "^application/x%-tar",
    "^image/",
    "^video/",
    "^audio/",
    "^font/",
}

local looks_like_file_upload = has_upload_length ~= nil
for _, pattern in ipairs(file_content_types) do
    if content_type:find(pattern) then
        looks_like_file_upload = true
        break
    end
end

if not looks_like_file_upload then
    return
end

ngx.status = ngx.HTTP_FORBIDDEN
ngx.header["Content-Type"] = "application/json"
ngx.say(cjson.encode({
    error = "upload_route_forbidden",
    message = "Uploads de arquivo sao permitidos apenas nas rotas de Storage",
}))
return ngx.exit(ngx.HTTP_FORBIDDEN)
