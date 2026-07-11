local storage_prefix = "/storage/v1"
local path = ngx.re.sub(ngx.var.uri, "^" .. storage_prefix, "", "jo")
local cjson = require("cjson")

ngx.req.read_body()
local body_data = ngx.req.get_body_data()

if body_data then
    local success, body = pcall(cjson.decode, body_data)
    if success and body then
        if ngx.var.request_method == "POST" and path == "/bucket" then
            if body.id then
                body.name = body.id
                body.id = nil
            end
        end
        if ngx.var.request_method == "POST" and ngx.re.match(path, "^/object/list/") then
            if body.path then
                body.prefix = body.path
                body.path = nil
            end
        end
        if ngx.var.request_method == "DELETE" and ngx.re.match(path, "^/object/[a-zA-Z0-9_-]+$") then
            if body.paths then
                body.prefixes = body.paths
                body.paths = nil
            end
        end
        if ngx.var.request_method == "POST" and ngx.re.match(path, "^/object/sign/") then
            if body.path then
                local clean_path = ngx.re.gsub(body.path, "^/", "", "jo")
                body.paths = { clean_path }
                body.path = nil
            end
        end       
        -- A API Storage aceita PUT para atualização; o Studio envia PATCH.
        if ngx.var.request_method == "PATCH" and ngx.re.match(path, "^/bucket/[a-zA-Z0-9]+$") then
            ngx.req.set_method(ngx.HTTP_PUT)
        end

        if ngx.var.request_method == "POST" and ngx.re.match(path, "^/object/move") then
            if body.from and body.to then
                -- O bucket está no path do Studio, mas no payload do upstream.
                local path_match = ngx.re.match(path, "^/object/move/([^/]+)")
                local bucket_id = path_match and path_match[1]

                if bucket_id then
                    body = {
                        bucketId = bucket_id,
                        sourceKey = body.from,
                        destinationBucket = bucket_id,
                        destinationKey = body.to
                    }
                    ngx.log(ngx.INFO, "Payload reorganizado para /object/move: ", cjson.encode(body))
                    
                    ngx.req.set_uri("/storage/v1/object/move", false)
                else
                    ngx.log(ngx.ERR, "Não foi possível extrair bucketId da URL: ", ngx.var.request_uri)
                end
            end
        end

        ngx.req.set_body_data(cjson.encode(body))
    else
        ngx.log(ngx.ERR, "Falha ao decodificar o corpo da requisição")
    end
end
