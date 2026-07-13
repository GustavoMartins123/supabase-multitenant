local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local http = require("resty.http")

local _M = {}

local function json_array(items)
    return setmetatable(items or {}, cjson.array_mt)
end

local function respond_json(status, payload)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say(cjson.encode(payload))
    return ngx.exit(status)
end

local function respond_upstream(res)
    ngx.status = res.status
    ngx.header["Content-Type"] = res.headers["Content-Type"]
        or res.headers["content-type"]
        or "application/json; charset=utf-8"

    if res.body and res.body ~= "" then
        ngx.print(res.body)
    end

    return ngx.exit(res.status)
end

local function storage_request(path, payload)
    local base_url = (ngx.var.server_path or ""):gsub("/+$", "")
    if base_url == "" then
        return nil, "server_path ausente"
    end

    local service_key = ngx.ctx.service_key
    if not service_key or service_key == "" then
        return nil, "service key ausente"
    end

    local encoded, encode_err = cjson_safe.encode(payload)
    if not encoded then
        return nil, "falha ao serializar payload: " .. tostring(encode_err)
    end

    local httpc = http.new()
    httpc:set_timeout(10000)

    return httpc:request_uri(base_url .. path, {
        method = "POST",
        body = encoded,
        ssl_verify = false,
        keepalive = false,
        headers = {
            ["Accept"] = "application/json",
            ["Authorization"] = "Bearer " .. service_key,
            ["apikey"] = service_key,
            ["Content-Type"] = "application/json",
            ["User-Agent"] = "studio-storage-compat/1.0",
        },
    })
end

local function decode_upstream_json(res, operation)
    local payload, decode_err = cjson_safe.decode(res.body or "")
    if type(payload) ~= "table" then
        return nil, string.format(
            "%s retornou JSON invalido: %s",
            operation,
            tostring(decode_err or "payload nao e objeto")
        )
    end

    return payload
end

local function fetch_full_index(vector_bucket_name, index_name)
    local res, request_err = storage_request("/storage/v1/vector/GetIndex", {
        vectorBucketName = vector_bucket_name,
        indexName = index_name,
    })

    if not res then
        return nil, {
            status = ngx.HTTP_BAD_GATEWAY,
            message = "Falha ao consultar GetIndex: " .. tostring(request_err),
        }
    end

    if res.status < 200 or res.status >= 300 then
        return nil, {
            upstream = res,
        }
    end

    local payload, decode_err = decode_upstream_json(res, "GetIndex")
    if not payload then
        return nil, {
            status = ngx.HTTP_BAD_GATEWAY,
            message = decode_err,
        }
    end

    if type(payload.index) ~= "table" then
        return nil, {
            status = ngx.HTTP_BAD_GATEWAY,
            message = "GetIndex retornou resposta sem index",
        }
    end

    return payload.index
end

local function handle_list_indexes()
    local vector_bucket_name = ngx.ctx.storage_platform_vector_bucket_name
    if not vector_bucket_name or vector_bucket_name == "" then
        return respond_json(ngx.HTTP_BAD_GATEWAY, {
            error = "storage_platform_vector_bucket_missing",
            message = "Nome do vector bucket nao foi preservado pelo router",
        })
    end

    local list_res, request_err = storage_request("/storage/v1/vector/ListIndexes", {
        vectorBucketName = vector_bucket_name,
        maxResults = 100,
    })

    if not list_res then
        return respond_json(ngx.HTTP_BAD_GATEWAY, {
            error = "storage_platform_upstream_unavailable",
            message = "Falha ao consultar ListIndexes: " .. tostring(request_err),
        })
    end

    if list_res.status < 200 or list_res.status >= 300 then
        return respond_upstream(list_res)
    end

    local list_payload, decode_err = decode_upstream_json(list_res, "ListIndexes")
    if not list_payload then
        return respond_json(ngx.HTTP_BAD_GATEWAY, {
            error = "storage_platform_invalid_upstream_json",
            message = decode_err,
        })
    end

    if type(list_payload.indexes) ~= "table" then
        return respond_json(ngx.HTTP_BAD_GATEWAY, {
            error = "storage_platform_invalid_upstream_shape",
            message = "ListIndexes retornou resposta sem indexes",
        })
    end

    local threads = {}
    for position, summary in ipairs(list_payload.indexes) do
        local index_name = type(summary) == "table" and summary.indexName or nil
        if type(index_name) ~= "string" or index_name == "" then
            return respond_json(ngx.HTTP_BAD_GATEWAY, {
                error = "storage_platform_invalid_upstream_shape",
                message = "ListIndexes retornou item sem indexName",
            })
        end

        threads[position] = ngx.thread.spawn(function()
            return fetch_full_index(vector_bucket_name, index_name)
        end)
    end

    local indexes = json_array({})
    for position, thread in ipairs(threads) do
        local thread_ok, index, index_err = ngx.thread.wait(thread)
        if not thread_ok then
            return respond_json(ngx.HTTP_BAD_GATEWAY, {
                error = "storage_platform_index_lookup_failed",
                message = "GetIndex falhou: " .. tostring(index),
            })
        end

        if not index then
            if index_err and index_err.upstream then
                return respond_upstream(index_err.upstream)
            end

            return respond_json((index_err and index_err.status) or ngx.HTTP_BAD_GATEWAY, {
                error = "storage_platform_index_lookup_failed",
                message = (index_err and index_err.message) or "GetIndex falhou",
            })
        end

        indexes[position] = index
    end

    local response = {
        indexes = indexes,
    }
    if list_payload.nextToken ~= nil and list_payload.nextToken ~= cjson.null then
        response.nextToken = list_payload.nextToken
    end

    return respond_json(ngx.HTTP_OK, response)
end

function _M.handle()
    if ngx.ctx.storage_platform_route ~= "vector_indexes_list" then
        return false
    end

    handle_list_indexes()
    return true
end

return _M
