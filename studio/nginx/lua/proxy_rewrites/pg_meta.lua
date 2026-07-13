local method = ngx.req.get_method()
local cjson = require("cjson.safe")

local uri = ngx.var.request_uri
if method == "GET"
    and uri:match("^/api/platform/pg%-meta/default/policies%?included_schemas=&excluded_schemas=$")
then
    ngx.req.set_uri("/policies", false)
    ngx.req.set_uri_args({})
    return
end

-- O Studio usa camelCase, enquanto postgres-meta recebe snake_case.
local function convert_fields(value)
    if type(value) ~= "table" then
        return value
    end

    local mappings = {
        tableId = "table_id",
        defaultValue = "default_value",
        defaultValueFormat = "default_value_format",
        isNullable = "is_nullable",
        isUnique = "is_unique",
        isGenerated = "is_generated",
        isIdentity = "is_identity",
        dataType = "data_type",
        ordinalPosition = "ordinal_position",
        identityGeneration = "identity_generation",
        isUpdatable = "is_updatable",
        dropDefault = "drop_default",
    }

    for camel_case, snake_case in pairs(mappings) do
        if value[camel_case] ~= nil then
            value[snake_case] = value[camel_case]
            value[camel_case] = nil
        end
    end

    for key, nested_value in pairs(value) do
        if type(nested_value) == "table" then
            value[key] = convert_fields(nested_value)
        end
    end

    return value
end

-- O SQL gerado pelo Studio self-hosted pressupoe um unico Storage em
-- host.docker.internal. Neste projeto o Studio e compartilhado e cada tenant tem
-- seu proprio Storage na rede Docker. O patch e estritamente limitado ao SQL de
-- criacao do S3 Vectors Wrapper e nunca toca consultas SQL comuns.
local function patch_s3_vectors_wrapper_query(body)
    if type(body) ~= "table" or type(body.query) ~= "string" then
        return body
    end

    local query = body.query
    if not query:find("s3_vectors_fdw_handler", 1, true)
        or not query:find("s3_vectors_fdw_validator", 1, true)
        or not query:find("endpoint_url", 1, true)
    then
        return body
    end

    local project_ref = ngx.var.project_ref
    if type(project_ref) ~= "string"
        or not project_ref:match("^[a-z_][a-z0-9_]*$")
        or #project_ref < 3 or #project_ref > 40
    then
        ngx.log(ngx.ERR, "Nao foi possivel resolver o projeto para o S3 Vectors Wrapper")
        return body
    end

    local endpoint = "http://supabase-storage-" .. project_ref .. ":5000/vector"
    local patched, replacements = query:gsub(
        "(endpoint_url%s+)'[^']*'",
        "%1'" .. endpoint .. "'"
    )

    if replacements == 0 then
        ngx.log(ngx.WARN, "SQL do S3 Vectors Wrapper sem endpoint_url substituivel")
        return body
    end

    body.query = patched
    ngx.log(ngx.INFO, "Endpoint do S3 Vectors Wrapper ajustado para o projeto: ", project_ref)
    return body
end

ngx.req.read_body()
local body_data = ngx.req.get_body_data()
if body_data and #body_data > 0 then
    local success, decoded_body = pcall(cjson.decode, body_data)
    if success and decoded_body then
        decoded_body = patch_s3_vectors_wrapper_query(convert_fields(decoded_body))
        local encoded_body, encode_err = cjson.encode(decoded_body)
        if encoded_body then
            ngx.req.set_body_data(encoded_body)
        else
            ngx.log(ngx.ERR, "Falha ao codificar JSON para pg-meta: ", encode_err)
        end
    else
        ngx.log(ngx.WARN, "Falha ao processar JSON: ", decoded_body or "formato inválido")
    end
end

local args = ngx.req.get_uri_args()
local id = args.id
if id then
    -- postgres-meta representa recursos individuais no path, não em ?id=.
    args.id = nil
    local resource = ngx.var.resource

    if not resource:match("/$") then
        resource = resource .. "/"
    end
    resource = resource .. id

    ngx.var.resource = resource
    ngx.req.set_uri_args(args)

    ngx.log(ngx.INFO, "URI atualizada: resource=", resource)
end
