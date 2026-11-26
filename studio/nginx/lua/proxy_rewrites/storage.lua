local module_arg = ...
local cjson = require("utils.json")
local internal_hmac = require("security.internal_hmac")
local platform_router = require("proxy_rewrites.storage_platform_router")

local M = {}
local storage_prefix = "/storage/v1"

local function json_array(items)
    return setmetatable(items or {}, cjson.array_mt)
end

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
    local body_data, read_err = internal_hmac.read_current_body()
    if body_data == nil then
        return nil, read_err or "falha ao ler corpo da requisicao"
    end
    if body_data == "" then
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

local function clear_uri_args()
    if ngx.req and ngx.req.set_uri_args then
        ngx.req.set_uri_args({})
    end
end

local function parse_list_query_args()
    if not ngx.req or not ngx.req.get_uri_args then
        return {}
    end

    local args, args_err = ngx.req.get_uri_args(100)
    if args_err == "truncated" then
        return nil, "Parametros de consulta em excesso", ngx.HTTP_BAD_REQUEST,
            "storage_platform_invalid_query"
    end
    if type(args) ~= "table" then
        return {}
    end

    local params = {}

    if args.prefix ~= nil then
        if type(args.prefix) ~= "string" then
            return nil, "prefix deve ser uma string", ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_prefix"
        end
        if args.prefix ~= "" then
            params.prefix = args.prefix
        end
    end

    if args.nextToken ~= nil then
        if type(args.nextToken) ~= "string" then
            return nil, "nextToken deve ser uma string", ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_next_token"
        end
        if args.nextToken ~= "" then
            params.nextToken = args.nextToken
        end
    end

    if args.maxResults ~= nil then
        if type(args.maxResults) ~= "string" or not args.maxResults:match("^[0-9]+$") then
            return nil, "maxResults deve ser um inteiro entre 1 e 500", ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_max_results"
        end
        local max_results = tonumber(args.maxResults)
        if not max_results or max_results < 1 or max_results > 500
            or max_results ~= math.floor(max_results)
        then
            return nil, "maxResults deve ser um inteiro entre 1 e 500", ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_max_results"
        end
        params.maxResults = max_results
    end

    return params
end

local function set_route_body(route)
    if route.body_mode == nil then
        return true
    end

    if route.body_mode == "vector_buckets_list" then
        local list_args, err, status, code = parse_list_query_args()
        if not list_args then
            return nil, err, status, code
        end
        return set_json_body(list_args)
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
        local list_args, err, status, code = parse_list_query_args()
        if not list_args then
            return nil, err, status, code
        end
        ngx.ctx.storage_platform_list_args = list_args
        local payload = {
            vectorBucketName = route.vector_bucket_name,
            maxResults = list_args.maxResults or 100,
        }
        if list_args.prefix ~= nil then
            payload.prefix = list_args.prefix
        end
        if list_args.nextToken ~= nil then
            payload.nextToken = list_args.nextToken
        end
        return set_json_body(payload)
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
            local status = err == "request body too large" and ngx.HTTP_REQUEST_ENTITY_TOO_LARGE or ngx.HTTP_BAD_REQUEST
            return nil, "Corpo JSON invalido: " .. tostring(err), status,
                "storage_platform_invalid_json"
        end

        local vector_bucket_name = body.bucketName
        if body.vectorBucketName ~= nil then
            return nil, "Use o campo canonico bucketName", ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_field"
        end
        if type(vector_bucket_name) ~= "string" or vector_bucket_name == "" then
            return nil, "bucketName e obrigatorio para criar um vector bucket",
                ngx.HTTP_BAD_REQUEST, "storage_platform_bucket_name_missing"
        end

        return set_json_body({ vectorBucketName = vector_bucket_name })
    end

    if route.body_mode == "vector_index_create" then
        local body, err = read_json_body()
        if not body then
            local status = err == "request body too large" and ngx.HTTP_REQUEST_ENTITY_TOO_LARGE or ngx.HTTP_BAD_REQUEST
            return nil, "Corpo JSON invalido: " .. tostring(err), status,
                "storage_platform_invalid_json"
        end

        local metadata_keys = body.metadataKeys
        if metadata_keys ~= nil and type(metadata_keys) ~= "table" then
            return nil, "metadataKeys deve ser uma lista de strings", ngx.HTTP_BAD_REQUEST,
                "storage_platform_invalid_metadata_keys"
        end
        if metadata_keys ~= nil then
            for position, value in pairs(metadata_keys) do
                if type(position) ~= "number" or position < 1 or position > #metadata_keys
                    or type(value) ~= "string" or value == ""
                then
                    return nil, "metadataKeys deve ser uma lista de strings nao vazias", ngx.HTTP_BAD_REQUEST,
                        "storage_platform_invalid_metadata_keys"
                end
            end
        end
        local payload = {
            vectorBucketName = route.vector_bucket_name,
            indexName = body.indexName,
            dataType = body.dataType,
            dimension = body.dimension,
            distanceMetric = body.distanceMetric,
        }
        -- This is an optional upstream field, but if present Storage requires
        -- at least one key. An empty list means no excluded metadata keys.
        if metadata_keys ~= nil and #metadata_keys > 0 then
            payload.metadataConfiguration = {
                nonFilterableMetadataKeys = json_array(metadata_keys),
            }
        end
        return set_json_body(payload)
    end

    return nil, "Modo de corpo do Storage nao reconhecido: " .. tostring(route.body_mode),
        ngx.HTTP_INTERNAL_SERVER_ERROR, "storage_platform_body_mode_unknown"
end

function M.rewrite()
local original_uri = ngx.var.uri or ""
local route, route_error = platform_router.resolve(original_uri, ngx.req.get_method())

if route and route.local_response then
    ngx.ctx.storage_platform_local_response = route
    return
end

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
    if route.route_name == "object_sign_multi" then
        ngx.ctx.sign_response_mode = "multi"
    end
    if route.uri and route.uri:find("^/storage/v1/vector/") ~= nil then
        clear_uri_args()
    end
    ngx.req.set_uri(route.uri, false)
elseif route_error then
    return reject(route_error)
end

local path = ngx.re.sub(ngx.var.uri, "^" .. storage_prefix, "", "jo")
local method = ngx.req.get_method()

-- A API Storage aceita PUT para atualizacao; o Studio envia PATCH.
if method == "PATCH" and ngx.re.match(path, "^/bucket/[^/]+$") then
    ngx.req.set_method(ngx.HTTP_PUT)
end

local is_json_rewrite_route = (
    (method == "POST" and (
        path == "/bucket"
        or ngx.re.match(path, "^/object/list/")
        or ngx.re.match(path, "^/object/sign/")
        or ngx.re.match(path, "^/object/move")
    ))
    or (method == "DELETE" and ngx.re.match(path, "^/object/[a-zA-Z0-9_-]+$"))
)

if not is_json_rewrite_route then
    return
end

local body_data, read_err = internal_hmac.read_current_body()
if body_data == nil then
    if read_err == "request body too large" then
        return reject({
            status = ngx.HTTP_REQUEST_ENTITY_TOO_LARGE,
            code = "storage_request_body_too_large",
            message = "Corpo JSON da requisicao excede o limite suportado",
        })
    end
    ngx.log(ngx.ERR, "Falha ao ler o corpo da requisicao do Storage: ", tostring(read_err))
    return
end

if body_data ~= "" then
    local body, decode_err = cjson.decode(body_data)
    if body and type(body) == "table" then
        local body_changed = false

        if method == "POST" and path == "/bucket" then
            if body.id then
                body.name = body.id
                body.id = nil
                body_changed = true
            end
        end

        if method == "POST" and ngx.re.match(path, "^/object/list/") then
            if body.path then
                body.prefix = body.path
                body.path = nil
                body_changed = true
            end
        end

        if method == "DELETE" and ngx.re.match(path, "^/object/[a-zA-Z0-9_-]+$") then
            if body.paths then
                body.prefixes = body.paths
                body.paths = nil
                body_changed = true
            end
        end

        if method == "POST" and ngx.re.match(path, "^/object/sign/") then
            if type(body.path) == "string" then
                body.paths = json_array({ ngx.re.gsub(body.path, "^/", "", "jo") })
                body.path = nil
                body_changed = true
            elseif type(body.path) == "table" then
                local paths = json_array({})
                for _, item in ipairs(body.path) do
                    if type(item) == "string" then
                        paths[#paths + 1] = ngx.re.gsub(item, "^/", "", "jo")
                    end
                end
                body.paths = paths
                body.path = nil
                body_changed = true
            end
        end

        if method == "POST" and ngx.re.match(path, "^/object/move") then
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
                    body_changed = true
                    ngx.req.set_uri("/storage/v1/object/move", false)
                else
                    ngx.log(ngx.ERR, "Nao foi possivel extrair bucketId da URL")
                end
            end
        end

        if body_changed then
            local encoded, encode_err = cjson.encode(body)
            if encoded then
                ngx.req.set_body_data(encoded)
            else
                ngx.log(ngx.ERR, "Falha ao codificar o corpo da requisicao do Storage: ", encode_err)
            end
        end
    elseif decode_err then
        ngx.log(ngx.DEBUG, "Corpo do Storage nao e JSON; mantendo payload original: ", decode_err)
    end
end
end

if type(module_arg) ~= "string" then
    return M.rewrite()
end

return M
