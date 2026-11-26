local cjson = require("cjson.safe")
local admin_groups = require("security.admin_groups")
local project_access = require("security.project_access")
local projects_api_signer = require("security.projects_api_signer")
local ref_resolver = require("project_context.project_ref_resolver")

local function reject(status, message, error_code, extra_headers)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    if type(extra_headers) == "table" then
        for name, value in pairs(extra_headers) do
            ngx.header[name] = value
        end
    end
    ngx.say(cjson.encode({
        error = error_code or "storage_s3_keys_error",
        detail = message,
        message = message,
    }))
    return ngx.exit(status)
end

local raw_request_uri = ngx.var.request_uri or ""
local path = raw_request_uri:match("^([^?]*)")
if path ~= ngx.var.uri then
    return reject(
        ngx.HTTP_BAD_REQUEST,
        "Invalid storage S3 keys path",
        "invalid_s3_keys_path"
    )
end

if ngx.req.get_method() ~= "GET" then
    return reject(
        ngx.HTTP_NOT_ALLOWED,
        "Method not allowed for storage S3 keys",
        "method_not_allowed",
        { Allow = "GET" }
    )
end

if (ngx.var.args and ngx.var.args ~= "") or raw_request_uri:find("?", 1, true) ~= nil then
    return reject(
        ngx.HTTP_BAD_REQUEST,
        "Unexpected query parameters for storage S3 keys",
        "unexpected_query_params"
    )
end

local ref = ngx.var.s3_keys_ref
if type(ref) ~= "string" or ref == "" then
    ref = (ngx.var.uri or ""):match("^/api/projects/([a-z]+)/storage/s3%-keys$")
end
if not ref_resolver.valid_ref(ref) then
    return reject(
        ngx.HTTP_BAD_REQUEST,
        "Invalid storage S3 keys path",
        "invalid_s3_keys_path"
    )
end

local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AUTH] Not authenticated")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local header_ref = ngx.var.http_x_studio_project_ref
if header_ref == nil or header_ref == "" then
    ngx.req.set_header("X-Studio-Project-Ref", ref)
end

local context = project_access.enforce(ref)
if type(context) ~= "table" then
    return
end

local is_global_admin = admin_groups.is_admin(ngx.ctx.canonical_groups or "")
if context.role ~= "admin" and not is_global_admin then
    return reject(
        ngx.HTTP_FORBIDDEN,
        "Only project administrators can access storage S3 keys",
        "project_access_denied"
    )
end

ngx.req.clear_header("Authorization")
ngx.req.clear_header("Proxy-Authorization")
ngx.req.clear_header("Cookie")

projects_api_signer.enforce()
