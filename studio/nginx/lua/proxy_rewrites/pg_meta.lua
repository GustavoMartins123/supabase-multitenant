local cjson = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")
local ref_resolver = require("project_context.project_ref_resolver")

local _M = {}

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

-- O wrapper assina o Host do endpoint. Cada projeto usa seu proprio Nginx como
-- fronteira confiavel; ele fixa o tenant UUID e encaminha ao Storage global.
-- O patch e limitado ao SQL de criacao do S3 Vectors Wrapper.
local function patch_s3_vectors_wrapper_query(body, context)
    if type(body) ~= "table" or type(body.query) ~= "string" then
        return body
    end

    local query = body.query
    if not query:find("s3_vectors_fdw_handler", 1, true)
        or not query:find("s3_vectors_fdw_validator", 1, true)
    then
        return body
    end

    local technical_name = context.technical_name
    if type(technical_name) ~= "string"
        or not technical_name:match("^[a-z_][a-z0-9_]*$")
        or #technical_name < 3 or #technical_name > 40
    then
        return nil, "Canonical technical name is required for the S3 Vectors Wrapper"
    end

    local endpoint = "http://supabase-nginx-" .. technical_name .. ":8080/vector"
    local patched, replacements = query:gsub(
        "(endpoint_url%s+)'[^']*'",
        "%1'" .. endpoint .. "'"
    )

    if replacements ~= 1 then
        return nil, "S3 Vectors Wrapper SQL requires exactly one endpoint_url"
    end

    body.query = patched
    return body
end

function _M.rewrite(context)
    if type(context) ~= "table" or not ref_resolver.valid_ref(context.ref)
        or context.ref ~= ngx.ctx.studio_request_project_ref
    then
        return nil, "Canonical project context is required"
    end

    local uri = ngx.var.request_uri
    if ngx.req.get_method() == "GET"
        and uri:match("^/api/platform/pg%-meta/[a-z]+/policies%?included_schemas=&excluded_schemas=$")
    then
        ngx.var.resource = "/policies"
        ngx.req.set_uri_args({})
        return true
    end

    local body_data, read_err = internal_hmac.read_current_body()
    if body_data == nil then
        return nil, read_err
    end
    if #body_data > 0 then
        local decoded_body, decode_err = cjson.decode(body_data)
        if type(decoded_body) ~= "table" or not body_data:match("^%s*{") then
            return nil, decode_err or "pg-meta requires a JSON object"
        end
        local rewritten, rewrite_err = patch_s3_vectors_wrapper_query(convert_fields(decoded_body), context)
        if not rewritten then
            return nil, rewrite_err
        end
        local encoded_body, encode_err = cjson.encode(rewritten)
        if not encoded_body then
            return nil, encode_err
        end
        ngx.req.set_body_data(encoded_body)
    end

    local args, args_err = ngx.req.get_uri_args()
    if args_err then return nil, "Invalid pg-meta query parameters" end
    local id = args.id
    if id ~= nil then
        if type(id) ~= "string" or id == "" or #id > 128 then
            return nil, "Invalid pg-meta resource id"
        end
        args.id = nil
        local resource = ngx.var.resource
        if type(resource) ~= "string" then
            return nil, "pg-meta resource is missing"
        end
        if not resource:match("/$") then
            resource = resource .. "/"
        end
        ngx.var.resource = resource .. ngx.escape_uri(id)
        ngx.req.set_uri_args(args)
    end
    return true
end

return _M
