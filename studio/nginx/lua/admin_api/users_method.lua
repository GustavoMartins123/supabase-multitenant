local module_arg = ...
local M = {}

function M.enforce()
    if ngx.var.request_method ~= "GET" then
        return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
    end
end

if type(module_arg) ~= "string" and ngx and ngx.var then
    M.enforce()
end

return M
