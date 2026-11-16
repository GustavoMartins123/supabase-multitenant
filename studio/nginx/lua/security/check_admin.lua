local groups = ngx.var.authelia_groups or ""
local email = ngx.var.authelia_email or ""
local admin_groups = require("security.admin_groups")
local user_context_headers = require("project_context.user_context_headers")
local is_admin = false

if email ~= "" then
    local _, canonical_groups = user_context_headers.apply(email, groups)
    groups = canonical_groups
    is_admin = admin_groups.is_admin(groups)
end

if not is_admin then
    ngx.log(ngx.WARN, "[ADMIN] Access denied - not admin")
    local method = ngx.var.request_method
    if method == "GET" then
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    else
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say('{"error": "Access denied"}')
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end
end

local uri = ngx.var.uri or ""
if uri == "/api/admin/projects-info" then
    require("admin_api.projects_info_method").enforce()
elseif uri:match("^/api/admin/projects/[^/]+/transfer/?$") then
    require("admin_api.projects_transfer_check").enforce()
elseif uri:match("^/api/admin/projects/[^/]+/?$") then
    require("admin_api.projects_delete_check").enforce()
end

require("security.projects_api_signer").enforce()
