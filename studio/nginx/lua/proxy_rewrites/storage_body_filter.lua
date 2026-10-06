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

    if not eof then
        ngx.arg[1] = nil
        return
    end

    ngx.ctx.sign_response_processed = true
    local raw_body = ngx.ctx.response_body
    local success, response_data = pcall(cjson.decode, raw_body)

    if not success or type(response_data) ~= "table" or #response_data == 0 then
        ngx.log(ngx.ERR, "signedURL is missing or null")
        ngx.arg[1] = raw_body
        return
    end

    local context = ngx.ctx.studio_project_context
    local origin = ngx.var.studio_public_origin or ""
    if type(context) ~= "table" or not context.ref or origin == "" then
        ngx.log(ngx.ERR, "Contexto do projeto ausente ao montar signed URL")
        ngx.arg[1] = raw_body
        return
    end

    local prefix = origin .. "/storage/v1/" .. context.ref .. "/"
    local function absolute(signed_url)
        return prefix .. ngx.re.gsub(signed_url, "^/", "", "jo")
    end

    cjson.encode_escape_forward_slash(false)

    if ngx.ctx.sign_response_mode == "multi" then
        local items = setmetatable({}, cjson.array_mt)
        for _, item in ipairs(response_data) do
            if type(item) == "table" then
                items[#items + 1] = {
                    path = item.path,
                    error = item.error,
                    signedUrl = item.signedURL and absolute(item.signedURL) or nil,
                }
            end
        end
        ngx.arg[1] = cjson.encode(items)
        return
    end

    local first_item = response_data[1]
    if type(first_item) ~= "table" or not first_item.signedURL then
        ngx.arg[1] = raw_body
        return
    end

    ngx.arg[1] = cjson.encode({ signedUrl = absolute(first_item.signedURL) })
end
