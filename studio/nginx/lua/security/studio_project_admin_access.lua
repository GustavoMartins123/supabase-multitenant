local context = require("security.project_access").enforce()
if type(context) ~= "table" then
    return
end

local groups = ngx.var.authelia_groups or ""
if not require("security.admin_groups").is_admin(groups) then
    ngx.log(ngx.ERR, "[ADMIN] Access denied - not admin. Groups: ", groups)
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say('{"error":"project_access_denied","message":"Access denied"}')
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end
