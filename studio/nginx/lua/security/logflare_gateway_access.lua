local cjson = require("cjson.safe")
local logflare_internal_guard = require("security.logflare_internal_guard")
local projects_api_signer = require("security.projects_api_signer")

local analytics_ok, analytics_status, analytics_code, analytics_message, analytics_allow =
    logflare_internal_guard.check()
if not analytics_ok then
    ngx.status = analytics_status or ngx.HTTP_UNAUTHORIZED
    ngx.header["Content-Type"] = "application/json"
    if analytics_allow then
        ngx.header["Allow"] = analytics_allow
    end
    ngx.say(cjson.encode({
        error = analytics_code or "analytics_internal_auth_failed",
        message = analytics_message or "Internal Analytics request rejected",
    }))
    return ngx.exit(ngx.status)
end

projects_api_signer.enforce()
