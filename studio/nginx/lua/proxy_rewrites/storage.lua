local cjson = require("cjson.safe")
local platform_router = require("proxy_rewrites.storage_platform_router")

local storage_prefix = "/storage/v1"

local function reject(problem)
    local status = problem.status or ngx.HTTP_BAD_REQUEST

    ngx.status = status
    ngx.header["Content-Type"] = "application/json"
    if problem.allow then
        ngx.header["Allow"] = problem.allow
    end

    ngx.say(cjson.encode({
        error = problem.code or "storage_platform_route_error",
        message = problem.message or "Falha ao mapear rota do Storage",
    }))

    return ngx.exit(status)
end

local function read_json_body()
    ngx.req.read_body()

    local body_data = ngx.req.get_body_data()
    if not body_data or body_data == "" then
        return {}
    end

    local body, err = cjson.decode(body_data)
    if not body or type(body) ~= "table" then
        return nil, err or "corpo JSON invalido"
    end

    return body
end

local function set_json_body(body)
    -- ngx.req.set_body_data exige que o corpo tenha sido inicializado antes,
    -- inclusive quando a requisicao original era GET e nao tinha payload.
    ngx.req.read_body()

    local encoded, err = cjson.encode(body)
    if not encoded then
        return nil, err
    end

    ngx.req.set_header("Content-Type", "application/json")
    ngx.req.set_body_data(encoded)
    return true
end

local function set_route_body(route)
    if route.body_mode == nil then
        return true
    end

    if route.body_mode == "empty_json_object" then
        return set_json_body({})
    end

    if route.body_mode == "vector_bucket_identity" then
        return set_json_body({
            vectorBucketName = route.vector_bucket_name,
        })
    end

    if route.body_mode == "vector_indexes_list" then
        return set_json_body({
            vectorBucketName = route.vector_bucket_name,
            maxResults = 100,
        })
    end

    if route.body_mode == "vector_index_identity" then
        return set_json_body({
            vectorBucketName = route.vector_bucket_name,
            indexName = route.index_name,
        })
    end

    if route.body_mode == "vector_bucket_create" then
        local body, err = read_json_body()
        if not body then
            return nil, "Corpo JSON invalido: " .. tostring(err), ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_json"
        end

        local vector_bucket_name = body.vectorBucketName or body.bucketName
        if type(vector_bucket_name) ~= "string" or vector_bucket_name == "" then
            return nil, "bucketName e obrigatorio para criar um vector bucket",
                ngx.HTTP_BAD_REQUEST, "storage_platform_bucket_name_missing"
        end

        return set_json_body({ vectorBucketName = vector_bucket_name })
    end

    if route.body_mode == "vector_index_create" then
        local body, err = read_json_body()
        if not body then
            return nil, "Corpo JSON invalido: " .. tostring(err), ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_json"
        end

        local metadata_keys = body.metadataKeys
        if type(metadata_keys) ~= "table" then
            metadata_keys = {}
        end

        return set_json_body({
            vectorBucketName = route.vector_bucket_name,
            indexName = body.indexName,
            dataType = body.dataType,
            dimension = body.dimension,
            distanceMetric = body.distanceMetric,
            metadataConfiguration = {
                nonFilterableMetadataKeys = metadata_keys,
            },
        })
    end

    return nil, "Modo de corpo do Storage nao reconhecido: " .. tostring(route.body_mode),
        ngx.HTTP_INTERNAL_SERVER_ERROR, "storage_platform_body_mode_unknown"
end

local original_uri = ngx.var.uri or ""
local route, route_error = platform_router.resolve(original_uri, ngx.req.get_method())

if route then
    local ok, err, status, code = set_route_body(route)
    if not ok then
        return reject({
            status = status or ngx.HTTP_INTERNAL_SERVER_ERROR,
            code = code or "storage_platform_body_encode_failed",
            message = err or "Falha ao preparar requisicao do Storage",
        })
    end

    if route.method == "POST" then
        ngx.req.set_method(ngx.HTTP_POST)
    elseif route.method == "PUT" then
        ngx.req.set_method(ngx.HTTP_PUT)
    elseif route.method == "DELETE" then
        ngx.req.set_method(ngx.HTTP_DELETE)
    end

    ngx.ctx.storage_platform_route = route.route_name
    ngx.ctx.storage_platform_response_mode = route.response_mode
    ngx.ctx.storage_platform_vector_bucket_name = route.vector_bucket_name
    ngx.ctx.storage_platform_index_name = route.index_name
    ngx.ctx.storage_platform_original_uri = original_uri
    ngx.req.set_uri(route.uri, false)
elseif route_error then
    return reject(route_error)
end

local path = ngx.re.sub(ngx.var.uri, "^" .. storage_prefix, "", "jo")

ngx.req.read_body()
local body_data = ngx.req.get_body_data()

if body_data then
    local body, decode_err = cjson.decode(body_data)
    if body and type(body) == "table" then
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
            if type(body.path) == "string" then
                local clean_path = ngx.re.gsub(body.path, "^/", "", "jo")
                body.paths = { clean_path }
                body.path = nil
            end
        end

        -- A API Storage aceita PUT para atualizacao; o Studio envia PATCH.
        if ngx.var.request_method == "PATCH" and ngx.re.match(path, "^/bucket/[^/]+$") then
            ngx.req.set_method(ngx.HTTP_PUT)
        end

        if ngx.var.request_method == "POST" and ngx.re.match(path, "^/object/move") then
            if body.from and body.to then
                -- O bucket esta no path do Studio, mas no payload do upstream.
                local path_match = ngx.re.match(path, "^/object/move/([^/]+)")
                local bucket_id = path_match and path_match[1]

                if bucket_id then
                    body = {
                        bucketId = bucket_id,
                        sourceKey = body.from,
                        destinationBucket = bucket_id,
                        destinationKey = body.to,
                    }
                    ngx.req.set_uri("/storage/v1/object/move", false)
                else
                    ngx.log(ngx.ERR, "Nao foi possivel extrair bucketId da URL: ", ngx.var.request_uri)
                end
            end
        end

        local encoded, encode_err = cjson.encode(body)
        if encoded then
            ngx.req.set_body_data(encoded)
        else
            ngx.log(ngx.ERR, "Falha ao codificar o corpo da requisicao do Storage: ", encode_err)
        end
    elseif decode_err then
        ngx.log(ngx.DEBUG, "Corpo do Storage nao e JSON; mantendo payload original: ", decode_err)
    end
end
