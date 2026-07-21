local uri = ngx.var.uri or ""

if uri == "/api/user/me/avatar" then
    return require("admin_api.user_avatar_handler").handle()
end

return require("admin_api.user_profile_handler").handle()
