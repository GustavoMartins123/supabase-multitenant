local cjson = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")

if ngx.req.get_method() ~= "GET" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local secret = os.getenv("PROJECTS_API_HMAC_SECRET") or ""
local max_skew = tonumber(os.getenv("INTERNAL_HMAC_MAX_SKEW_SECONDS")) or 60
local ok, verify_status = internal_hmac.verify_current_request(
    secret,
    "projects-api",
    { max_skew = max_skew }
)
if not ok then
    return ngx.exit(verify_status or ngx.HTTP_FORBIDDEN)
end

local metrics = ngx.shared.service_key_metrics
ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    hit = metrics:get("hit") or 0,
    miss = metrics:get("miss") or 0,
    version_reload = metrics:get("version_reload") or 0,
    invalidation = metrics:get("invalidation") or 0,
    fetch_error = metrics:get("fetch_error") or 0,
    fetch_error_backoff = metrics:get("fetch_error_backoff") or 0,
    stale_fetch = metrics:get("stale_fetch") or 0,
    version_check_error = metrics:get("version_check_error") or 0,
}))
