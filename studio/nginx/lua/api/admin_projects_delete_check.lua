-- Método deve ser DELETE para exclusão
if ngx.var.request_method ~= "DELETE" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error": "Method not allowed - use DELETE"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

-- Verificar se o header X-Delete-Password está presente
local delete_password = ngx.var.http_x_delete_password
if not delete_password or delete_password == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "X-Delete-Password header is required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

ngx.log(ngx.INFO, "[DELETE_PROJECT] Admin access granted for user: ", ngx.var.authelia_email)
