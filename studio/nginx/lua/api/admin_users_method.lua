if ngx.var.request_method ~= "GET" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end
