local email = ngx.var.authelia_email
local admin_groups = require("security.admin_groups")
if not email or email == "" then return ngx.exit(401) end
local user_id, groups, entry = require("project_context.user_context_headers").apply(email)
ngx.var.username = entry.username
ngx.var.display_name = entry.display_name
ngx.var.user_id = user_id
ngx.var.myrole = admin_groups.is_admin(groups) and "true" or "false"
