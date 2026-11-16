local module_arg = ...
local M = {}

function M.enforce()
    if ngx.var.request_method ~= "POST" then
        ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
        ngx.say('{"error": "Method not allowed"}')
        return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
    end

    local user_id = ngx.var[1]
    if not user_id or user_id == "" then
        ngx.status = ngx.HTTP_BAD_REQUEST
        ngx.say('{"error": "User ID is required"}')
        return ngx.exit(ngx.HTTP_BAD_REQUEST)
    end
end

if type(module_arg) ~= "string" and ngx and ngx.var then
    M.enforce()
end

return M
