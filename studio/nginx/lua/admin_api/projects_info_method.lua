if ngx.var.request_method ~= "POST" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error": "Método não permitido"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end
