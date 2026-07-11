local cjson = require("cjson.safe")
local shared_token = require("security.shared_token")

local headers = ngx.req.get_headers()
local supplied_token = headers["X-Shared-Token"] or ""
local internal_service = headers["X-Internal-Service"]

if internal_service ~= "projects-api" or not shared_token.matches(supplied_token) then
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end
if ngx.req.get_method() ~= "POST" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local project_ref = ngx.var.cache_ref
local version_check_ttl = tonumber(
    os.getenv("SERVICE_KEY_VERSION_CHECK_TTL_SECONDS")
) or 5
version_check_ttl = math.max(1, math.min(version_check_ttl, 3600))
ngx.req.read_body()
local body = cjson.decode(ngx.req.get_body_data() or "{}") or {}
local version = tonumber(body.project_key_version)
if not project_ref or project_ref == "" or not version or version < 1 then
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local cache = ngx.shared.service_keys
cache:delete("service_key:value:" .. project_ref)
cache:delete("service_key:cached_version:" .. project_ref)
cache:set("service_key:required_version:" .. project_ref, version)
cache:set("service_key:checked_version:" .. project_ref, version, version_check_ttl)
ngx.shared.service_key_metrics:incr("invalidation", 1, 0)

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    invalidated = true,
    project_ref = project_ref,
    project_key_version = version,
}))
