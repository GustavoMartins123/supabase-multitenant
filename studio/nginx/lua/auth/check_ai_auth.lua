local email = ngx.var.authelia_email
if not email or email == "" then
    ngx.log(ngx.ERR, "[AI] Não autenticado")
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

if ngx.var.request_method ~= "POST" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error": "Use POST method"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end
