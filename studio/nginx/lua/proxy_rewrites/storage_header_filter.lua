local path = ngx.var.uri
if ngx.var.request_method == "POST" and ngx.re.match(path, "/storage/v1/object/sign/") then
    ngx.ctx.process_sign_response = true
    ngx.header.content_length = nil
end
