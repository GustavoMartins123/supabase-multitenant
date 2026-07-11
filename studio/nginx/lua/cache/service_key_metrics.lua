local cjson = require("cjson.safe")
local shared_token = require("security.shared_token")

local headers = ngx.req.get_headers()
if ngx.req.get_method() ~= "GET" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end
if headers["X-Internal-Service"] ~= "projects-api"
    or not shared_token.matches(headers["X-Shared-Token"])
then
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

local metrics = ngx.shared.service_key_metrics
ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    hit = metrics:get("hit") or 0,
    miss = metrics:get("miss") or 0,
    version_reload = metrics:get("version_reload") or 0,
    invalidation = metrics:get("invalidation") or 0,
    fetch_error = metrics:get("fetch_error") or 0,
    version_check_error = metrics:get("version_check_error") or 0,
}))
