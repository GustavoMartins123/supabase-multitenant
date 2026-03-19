ngx.header.content_type = "application/json; charset=utf-8"
ngx.status = ngx.HTTP_OK
ngx.say('{}')
return ngx.exit(ngx.HTTP_OK)
