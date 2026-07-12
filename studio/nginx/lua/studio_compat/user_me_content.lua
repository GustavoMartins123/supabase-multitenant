local uri = ngx.var.uri or ""

if uri == "/api/user/me/avatar" or uri:match("^/api/user/me/avatar/[0-9a-fA-F%-]+$") then
    return require("admin_api.user_avatar_handler").handle()
end

return require("admin_api.user_profile_handler").handle()
