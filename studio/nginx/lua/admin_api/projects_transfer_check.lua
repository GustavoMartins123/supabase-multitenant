local module_arg = ...
local M = {}

function M.enforce()
    if ngx.var.request_method ~= "POST" then
        ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
        ngx.say('{"error":"Method not allowed - use POST"}')
        return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
    end
end

if type(module_arg) ~= "string" and ngx and ngx.var then
    M.enforce()
end

return M
