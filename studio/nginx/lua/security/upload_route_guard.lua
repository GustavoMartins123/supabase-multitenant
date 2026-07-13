local cjson = require("cjson.safe")

local method = ngx.req.get_method()
local uri = ngx.var.uri or ""

-- O Studio oficial consulta /api/get-s3-keys antes de criar o S3 Vectors FDW.
-- Como este Studio e compartilhado, as chaves precisam vir do projeto selecionado
-- e passar pelo Projects API, que valida membership/admin e le o .env do tenant.
if uri == "/api/get-s3-keys" then
    if method ~= "GET" then
        ngx.status = ngx.HTTP_NOT_ALLOWED
        ngx.header["Allow"] = "GET"
        ngx.header["Content-Type"] = "application/json"
        ngx.say(cjson.encode({
            error = "method_not_allowed",
            message = "Use GET para consultar as credenciais S3 Vectors",
        }))
        return ngx.exit(ngx.HTTP_NOT_ALLOWED)
    end

    local resolver = require("project_context.project_ref_resolver")
    local project_ref = resolver.resolve()
    if project_ref == "default" then
        ngx.status = ngx.HTTP_CONFLICT
        ngx.header["Content-Type"] = "application/json"
        ngx.header["Cache-Control"] = "no-store"
        ngx.say(cjson.encode({
            error = "project_not_selected",
            message = "Selecione um projeto antes de instalar o S3 Vectors Wrapper",
        }))
        return ngx.exit(ngx.HTTP_CONFLICT)
    end

    return ngx.req.set_uri(
        "/api/projects/" .. project_ref .. "/storage/s3-keys",
        true
    )
end

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
