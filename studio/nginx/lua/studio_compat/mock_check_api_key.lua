ngx.header.content_type = "application/json; charset=utf-8"
ngx.status = ngx.HTTP_OK
ngx.say('{"hasKey": true}')
ngx.log(ngx.INFO, "[MOCK-AI-CHECK-KEY] Mock check-api-key returned for: ", ngx.var.authelia_email)
return ngx.exit(ngx.HTTP_OK)
