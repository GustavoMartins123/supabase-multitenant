local _M = {}

local function target(uri, options)
    options = options or {}
    options.uri = uri
    return options
end

local function method_not_allowed(resource, allow)
    return nil, {
        status = 405,
        code = "storage_platform_method_not_allowed",
        message = "Metodo nao suportado para " .. resource,
        allow = allow,
    }
end

local function platform_path(uri)
    if type(uri) ~= "string" then
        return nil
    end

    local path = uri:match("^/api/platform/storage/[^/]+(.*)$")
    if path == nil then
        return nil
    end

    if path == "" then
        return "/"
    end

    return path
end

local object_actions = {
    list = "list",
    sign = "sign",
    move = "move",
}

function _M.resolve(uri, method)
    local path = platform_path(uri)
    if not path then
        return nil
    end

    method = string.upper(method or "GET")

    -- Buckets e objetos usam a API REST tradicional do Storage.
    if path == "/buckets" then
        return target("/storage/v1/bucket")
    end

    local bucket_id = path:match("^/buckets/([^/]+)$")
    if bucket_id then
        return target("/storage/v1/bucket/" .. bucket_id)
    end

    bucket_id = path:match("^/buckets/([^/]+)/empty$")
    if bucket_id then
        return target("/storage/v1/bucket/" .. bucket_id .. "/empty")
    end

    local object_bucket, object_action = path:match("^/buckets/([^/]+)/objects/([^/]+)$")
    if object_bucket and object_action then
        if object_action == "download" then
            return target("/storage/v1/object/" .. object_bucket)
        end

        local upstream_action = object_actions[object_action]
        if upstream_action then
            return target("/storage/v1/object/" .. upstream_action .. "/" .. object_bucket)
        end
    end

    object_bucket = path:match("^/buckets/([^/]+)/objects$")
    if object_bucket then
        return target("/storage/v1/object/" .. object_bucket)
    end

    -- O Studio usa endpoints REST de plataforma, mas o Storage API implementa
    -- Vector Buckets como operacoes POST no namespace /vector.
    if path == "/vector-buckets" then
        if method == "GET" then
            return target("/storage/v1/vector/ListVectorBuckets", {
                method = "POST",
                body_mode = "empty_json_object",
                route_name = "vector_buckets_list",
            })
        end

        if method == "POST" then
            return target("/storage/v1/vector/CreateVectorBucket", {
                method = "POST",
                body_mode = "vector_bucket_create",
                route_name = "vector_bucket_create",
            })
        end

        return method_not_allowed("vector-buckets", "GET, POST")
    end

    -- '-' e um quantificador especial em patterns Lua. Ele precisa ser escapado
    -- como '%-' quando a familia /vector-buckets e reconhecida por string.match.
    local vector_bucket_name, index_name = path:match(
        "^/vector%-buckets/([^/]+)/indexes/([^/]+)$"
    )
    if vector_bucket_name and index_name then
        if method == "DELETE" then
            return target("/storage/v1/vector/DeleteIndex", {
                method = "POST",
                body_mode = "vector_index_identity",
                route_name = "vector_index_delete",
                vector_bucket_name = vector_bucket_name,
                index_name = index_name,
            })
        end

        return method_not_allowed("vector bucket index", "DELETE")
    end

    vector_bucket_name = path:match("^/vector%-buckets/([^/]+)/indexes$")
    if vector_bucket_name then
        if method == "GET" then
            return target("/storage/v1/vector/ListIndexes", {
                method = "POST",
                body_mode = "vector_indexes_list",
                route_name = "vector_indexes_list",
                vector_bucket_name = vector_bucket_name,
            })
        end

        if method == "POST" then
            return target("/storage/v1/vector/CreateIndex", {
                method = "POST",
                body_mode = "vector_index_create",
                route_name = "vector_index_create",
                vector_bucket_name = vector_bucket_name,
            })
        end

        return method_not_allowed("vector bucket indexes", "GET, POST")
    end

    vector_bucket_name = path:match("^/vector%-buckets/([^/]+)$")
    if vector_bucket_name then
        if method == "GET" then
            return target("/storage/v1/vector/GetVectorBucket", {
                method = "POST",
                body_mode = "vector_bucket_identity",
                response_mode = "unwrap_vector_bucket",
                route_name = "vector_bucket_get",
                vector_bucket_name = vector_bucket_name,
            })
        end

        if method == "DELETE" then
            return target("/storage/v1/vector/DeleteVectorBucket", {
                method = "POST",
                body_mode = "vector_bucket_identity",
                route_name = "vector_bucket_delete",
                vector_bucket_name = vector_bucket_name,
            })
        end

        return method_not_allowed("vector bucket", "GET, DELETE")
    end

    return nil, {
        status = 404,
        code = "storage_platform_route_unmapped",
        message = "Rota de compatibilidade do Storage ainda nao mapeada: " .. path,
    }
end

return _M
