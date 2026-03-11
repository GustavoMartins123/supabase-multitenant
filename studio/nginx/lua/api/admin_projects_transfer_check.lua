if ngx.var.request_method ~= "POST" then   -- <- transferência é POST
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error":"Method not allowed – use POST"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end
