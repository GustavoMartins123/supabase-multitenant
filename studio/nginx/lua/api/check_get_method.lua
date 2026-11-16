local module_arg = ...
local M = {}

function M.enforce()
    if ngx.var.request_method ~= "GET" then
        ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
        ngx.header["Allow"] = "GET"
        ngx.say('{"error": "Method Not Allowed"}')
        return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
    end
end

if type(module_arg) ~= "string" and ngx and ngx.var then
    M.enforce()
end

return M
