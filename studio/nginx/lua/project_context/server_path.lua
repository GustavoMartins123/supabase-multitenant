local server_domain = ngx.var.server_domain
local project_ref = ngx.var.project_ref

return server_domain .. "/" .. project_ref .. "/"
