local storage_prefix = "/storage/v1"
local path = ngx.re.sub(ngx.var.uri, "^" .. storage_prefix, "", "jo")
ngx.req.read_body()
local data = ngx.req.get_body_data()

if data then
    local cjson = require "cjson"
    local success, body = pcall(cjson.decode, data)
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
        -- Para atualizar uma bucket existente, pois o storage espera um 'put' e não um patch 'https://supabase.github.io/storage/#/'
        if ngx.var.request_method == "PATCH" and ngx.re.match(path, "^/bucket/[a-zA-Z0-9]+$") then
            ngx.req.set_method(ngx.HTTP_PUT)
        end

        if ngx.var.request_method == "POST" and ngx.re.match(path, "^/object/move") then
            if body.from and body.to then
                -- Capturar o bucketId da URI original antes do rewrite
                local bucketId = ngx.re.match(path, "^/object/move/([^/]+)")[1]
                
                if bucketId then
                    -- Monta o novo payload
                    body = {
                        bucketId = bucketId,
                        sourceKey = body.from,
                        destinationBucket = bucketId,
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
        ngx.log(ngx.ERR, "Falha ao decodificar o corpo da requisição: ", data)
    end
end
