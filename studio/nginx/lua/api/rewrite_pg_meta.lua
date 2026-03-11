local method = ngx.req.get_method()

ngx.req.read_body()
local data = ngx.req.get_body_data()
local cjson = require "cjson.safe"

local uri    = ngx.var.request_uri
if method == "GET"
    and uri:match("^/api/platform/pg%-meta/default/policies%?included_schemas=&excluded_schemas=$")
then
    ngx.req.set_uri("/policies", false)
    ngx.req.set_uri_args({})
    return
end

local function convert_fields(obj)
    if type(obj) ~= "table" then
        return obj
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
    
    for camel, snake in pairs(mappings) do
        if obj[camel] ~= nil then
            obj[snake] = obj[camel]
            obj[camel] = nil
        end
    end
    
    for k, v in pairs(obj) do
        if type(v) == "table" then
            obj[k] = convert_fields(v)
        end
    end
    
    return obj
end

ngx.req.read_body()
local data = ngx.req.get_body_data()
if data and #data > 0 then
    local cjson = require "cjson.safe"
    local success, js = pcall(cjson.decode, data)
    if success and js then
        js = convert_fields(js)
        ngx.req.set_body_data(cjson.encode(js))
    else
        ngx.log(ngx.WARN, "Falha ao processar JSON: ", (js or "formato inválido"))
    end
end

local args = ngx.req.get_uri_args()
local id = args["id"]
local keys
if id then
    args["id"] = nil
    
    local project_ref = ngx.var.project_ref
    
    local resource = ngx.var.resource
    
    if not resource:match("/$") then
        resource = resource .. "/"
    end
    resource = resource .. id
    
    ngx.var.resource = resource
    
    ngx.req.set_uri_args(args)
    
    ngx.log(ngx.INFO, "URI atualizada: resource=" .. resource)
end
