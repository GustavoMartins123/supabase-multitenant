local cjson_safe = require("cjson.safe")
local global_escape = type(cjson_safe.encode_escape_forward_slash) == "function"
    and cjson_safe.encode_escape_forward_slash()
local json = type(cjson_safe.new) == "function" and cjson_safe.new() or cjson_safe

assert(json.array_mt and json.decode_array_with_array_mt, "JSON array support is required")
json.decode_array_with_array_mt(true)
json.encode_empty_table_as_object(true)

if type(json.encode_escape_forward_slash) == "function" and json ~= cjson_safe then
    local raw_encode = json.encode
    if global_escape ~= nil then
        cjson_safe.encode_escape_forward_slash(global_escape)
    end
    function json.encode(...)
        local restore = cjson_safe.encode_escape_forward_slash()
        json.encode_escape_forward_slash(false)
        local encoded, err = raw_encode(...)
        cjson_safe.encode_escape_forward_slash(restore ~= false)
        if encoded == nil then
            return nil, err
        end
        return encoded
    end
else
    json.encode_escape_forward_slash(false)
end

return json
