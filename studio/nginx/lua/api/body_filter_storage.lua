if ngx.ctx.process_sign_response and not ngx.ctx.sign_response_processed then
    local cjson = require "cjson"
    local chunk = ngx.arg[1]
    local eof = ngx.arg[2]
    
    ngx.ctx.response_body = (ngx.ctx.response_body or "") .. (chunk or "")
    
    if eof then
        ngx.ctx.sign_response_processed = true
        local success, response_data = pcall(cjson.decode, ngx.ctx.response_body)
        
        if success and response_data and type(response_data) == "table" and #response_data > 0 then
            local first_item = response_data[1]
            ngx.log(ngx.ERR, "DEBUG first_item: ", cjson.encode(first_item))
            if first_item and first_item.signedURL then
                local server_path = ngx.var.server_path or ""
                server_path = ngx.re.gsub(server_path, "/$", "", "jo")
                local signed_url = ngx.re.gsub(first_item.signedURL, "^/", "", "jo")
                local full_url = server_path .. "/storage/v1/" .. signed_url
                cjson.encode_escape_forward_slash(false)
                local result = { signedUrl = full_url }
                
                ngx.arg[1] = cjson.encode(result)
            else
                ngx.arg[1] = ngx.ctx.response_body
            end
        else
            ngx.log(ngx.ERR, "signedURL is missing or null")
            ngx.arg[1] = ngx.ctx.response_body
        end
    else
        ngx.arg[1] = nil
    end
end
