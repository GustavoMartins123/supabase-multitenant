local ref = ngx.var.cookie_supabase_session_project or "default"
return ngx.var.server_domain .. "/" .. ngx.var.project_ref .. "/"
