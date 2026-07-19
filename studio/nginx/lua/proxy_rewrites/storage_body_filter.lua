local cjson = require("cjson")

local function process_platform_response()
    local mode = ngx.ctx.storage_platform_response_mode
    if not mode or ngx.ctx.storage_platform_response_processed then
        return false
    end

    local chunk = ngx.arg[1]
    local eof = ngx.arg[2]
    ngx.ctx.storage_platform_response_body =
        (ngx.ctx.storage_platform_response_body or "") .. (chunk or "")

    if not eof then
        ngx.arg[1] = nil
        return true
    end

    ngx.ctx.storage_platform_response_processed = true
    local raw_body = ngx.ctx.storage_platform_response_body or ""

    -- Erros do Storage API devem atravessar sem alteracao para nao esconder a
    -- causa real de falhas de provider, migration, permissao ou validacao.
    if ngx.status < 200 or ngx.status >= 300 then
        ngx.arg[1] = raw_body
        return true
    end

    local success, response_data = pcall(cjson.decode, raw_body)
    if not success or type(response_data) ~= "table" then
        ngx.log(ngx.ERR, "Resposta JSON invalida do Storage API em ", tostring(mode))
        ngx.arg[1] = raw_body
        return true
    end

    if mode == "unwrap_vector_bucket" then
        if type(response_data.vectorBucket) ~= "table" then
            ngx.log(ngx.ERR, "GetVectorBucket retornou resposta sem vectorBucket")
            ngx.arg[1] = raw_body
            return true
        end

        ngx.arg[1] = cjson.encode(response_data.vectorBucket)
        return true
    end

    ngx.log(ngx.ERR, "Modo de resposta do Storage nao reconhecido: ", tostring(mode))
    ngx.arg[1] = raw_body
    return true
end

if process_platform_response() then
    return
end

if ngx.ctx.process_sign_response and not ngx.ctx.sign_response_processed then
    local chunk = ngx.arg[1]
    local eof = ngx.arg[2]

    ngx.ctx.response_body = (ngx.ctx.response_body or "") .. (chunk or "")

    if eof then
        ngx.ctx.sign_response_processed = true
        local success, response_data = pcall(cjson.decode, ngx.ctx.response_body)

        if success and response_data and type(response_data) == "table" and #response_data > 0 then
            local first_item = response_data[1]
            if first_item and first_item.signedURL then
                local context = ngx.ctx.studio_project_context
                local public_origin = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
                if type(context) ~= "table" or not context.ref or public_origin == "" then
                    ngx.log(ngx.ERR, "Contexto do projeto ausente ao montar signed URL")
                    ngx.arg[1] = ngx.ctx.response_body
                    return
                end

                local signed_url = ngx.re.gsub(first_item.signedURL, "^/", "", "jo")
                local full_url = public_origin .. "/" .. context.ref .. "/storage/v1/" .. signed_url
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
