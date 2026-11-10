local csrf = require("security.csrf")
if not csrf.enforce() then return end
local method = ngx.req.get_method()
if method ~= 'GET' and method ~= 'POST' and method ~= 'PUT' and method ~= 'DELETE' then
    return ngx.exit(ngx.HTTP_NOT_ALLOWED)
end
if method ~= 'GET' and not csrf.require_json() then return end
local email = ngx.var.authelia_email
if not email or email == "" then return ngx.exit(ngx.HTTP_UNAUTHORIZED) end
require("project_context.user_context_headers").apply(email, ngx.var.authelia_groups or "")
require("security.projects_api_signer").enforce()
