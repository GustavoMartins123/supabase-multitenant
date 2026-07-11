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
        dataType             = "data_type",
        ordinalPosition      = "ordinal_position",
        identityGeneration   = "identity_generation",
        isUpdatable          = "is_updatable",
        dropDefault         = "drop_default",
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

ngx.req.read_body()
local body_data = ngx.req.get_body_data()
if body_data and #body_data > 0 then
    local success, decoded_body = pcall(cjson.decode, body_data)
    if success and decoded_body then
        decoded_body = convert_fields(decoded_body)
        ngx.req.set_body_data(cjson.encode(decoded_body))
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
