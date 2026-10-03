local cjson = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")
local service_key_version = require("cache.service_key_version")
local ref_resolver = require("project_context.project_ref_resolver")

if ngx.req.get_method() ~= "POST" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local verified, verify_status, verify_err = internal_hmac.verify_current_request(
    os.getenv("PROJECTS_API_HMAC_SECRET") or "",
    "projects-api",
    {
        max_skew = tonumber(os.getenv("INTERNAL_HMAC_MAX_SKEW_SECONDS")) or 60,
    }
)
if not verified then
    ngx.log(
        ngx.WARN,
        "[INTERNAL-HMAC] Cache invalidation rejected: ",
        verify_err or "unknown"
    )
    return ngx.exit(verify_status or ngx.HTTP_FORBIDDEN)
end

local project_ref = ngx.var.cache_ref
local raw_body, read_err = internal_hmac.read_current_body()
if raw_body == nil then
    ngx.log(ngx.ERR, "Invalid cache invalidation body: ", read_err)
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end
local body = cjson.decode(raw_body)
if type(body) ~= "table" or not raw_body:match("^%s*{") then
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end
local version = tonumber(body.project_key_version)
if not ref_resolver.valid_ref(project_ref) or not version or version < 1 or version % 1 ~= 0 then
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local required_version, version_err = service_key_version.invalidate(
    project_ref,
    version
)
if not required_version then
    ngx.log(ngx.ERR, "Falha ao invalidar service key: ", version_err)
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
ngx.shared.service_key_metrics:incr("invalidation", 1, 0)

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    invalidated = true,
    project_ref = project_ref,
    project_key_version = required_version,
}))
