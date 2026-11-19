package.path = "studio/nginx/lua/?.lua;studio/nginx/lua/?/init.lua;" .. package.path

if not pcall(require, "cjson.safe") then
    local function make_cjson()
        local inst = {
            array_mt = {},
            decode_array_with_array_mt = function() end,
            encode_empty_table_as_object = function() end,
            encode_escape_forward_slash = function() return true end,
            decode = function(raw)
                if raw == '{"tableId":7}' then
                    return { tableId = 7 }
                end
                return nil, "invalid json"
            end,
            encode = function(tbl)
                if type(tbl) == "table" and tbl.table_id == 7 and tbl.tableId == nil then
                    return '{"table_id":7}'
                end
                if type(tbl) == "table" and tbl.error then
                    return string.format('{"error":"%s","message":"%s"}', tostring(tbl.error), tostring(tbl.message or ""))
                end
                return "{}"
            end,
        }
        inst.new = function()
            return {
                array_mt = inst.array_mt,
                decode_array_with_array_mt = inst.decode_array_with_array_mt,
                encode_empty_table_as_object = inst.encode_empty_table_as_object,
                encode_escape_forward_slash = inst.encode_escape_forward_slash,
                decode = inst.decode,
                encode = inst.encode,
            }
        end
        return inst
    end
    package.preload["cjson.safe"] = make_cjson
end

local request_state = {
    method = "GET",
    body = "",
    args = {},
    args_err = nil,
    uri_args_set = nil,
    body_set = nil,
}

package.loaded["security.internal_hmac"] = {
    read_current_body = function()
        return request_state.body
    end,
}

local REF = "abcdefghijklmnopqrst"

_G.ngx = {
    HTTP_BAD_REQUEST = 400,
    HTTP_UNAUTHORIZED = 401,
    HTTP_SERVICE_UNAVAILABLE = 503,
    ERR = 3,
    status = 200,
    header = {},
    ctx = {
        studio_request_project_ref = REF,
    },
    var = {
        request_uri = "/api/platform/pg-meta/" .. REF .. "/tables",
        resource = "/tables",
    },
    req = {
        get_method = function()
            return request_state.method
        end,
        get_uri_args = function()
            return request_state.args, request_state.args_err
        end,
        set_uri_args = function(updated)
            request_state.uri_args_set = updated
        end,
        set_body_data = function(updated)
            request_state.body_set = updated
        end,
        set_header = function() end,
    },
    escape_uri = function(val)
        -- RFC 3986 / OpenResty ngx.escape_uri keeps unreserved chars including '.'
        return (tostring(val):gsub("[^%w%-_%.~]", function(ch)
            return string.format("%%%02X", ch:byte())
        end))
    end,
    say = function(msg)
        request_state.said = msg
    end,
    exit = function(code)
        request_state.exited = code
        return code
    end,
    log = function() end,
}

local pg_meta = require("proxy_rewrites.pg_meta")
local context = { ref = REF, technical_name = "alpha_proj" }

local function reset(args, args_err, body, method)
    request_state.method = method or "GET"
    request_state.body = body or ""
    request_state.args = args or {}
    request_state.args_err = args_err
    request_state.uri_args_set = nil
    request_state.body_set = nil
    request_state.said = nil
    request_state.exited = nil
    ngx.var.resource = "/tables"
    ngx.var.request_uri = "/api/platform/pg-meta/" .. REF .. "/tables"
    ngx.ctx.studio_request_project_ref = REF
end

-- 1. Rejects truncated query parameters (query-smuggling defense)
reset({ a = "1" }, "truncated")
local ok, err = pg_meta.rewrite(context)
assert(ok == nil and err == "Too many pg-meta query parameters", "expected truncated rejection, got: " .. tostring(err))
assert(ngx.var.resource == "/tables")

-- 2. Rejects dot segments, traversal, slashes, non-string tables/booleans, empty, overlong, and disallowed chars
local invalid_ids = {
    ".",
    "..",
    "foo..bar",
    "..tables",
    "tables..",
    "../query",
    "1/2",
    "1\\2",
    "1%2f2",
    "1?x=1",
    "1#frag",
    "bad space",
    "",
    ("x"):rep(129),
    { "1", "2" },
    true,
}

for _, bad_id in ipairs(invalid_ids) do
    reset({ id = bad_id, included_schemas = "public" })
    local res, res_err = pg_meta.rewrite(context)
    assert(res == nil and res_err == "Invalid pg-meta resource id",
        "expected Invalid pg-meta resource id for " .. tostring(bad_id) .. ", got: " .. tostring(res) .. " / " .. tostring(res_err))
    assert(ngx.var.resource == "/tables", "resource mutated on invalid id: " .. tostring(ngx.var.resource))
    assert(request_state.uri_args_set == nil)
end

-- 3. Accepts valid identifiers (numeric OID, UUID, schema.name, colon/hyphen/underscore) and escapes cleanly
local valid_cases = {
    { id = "16384", expected = "/tables/16384" },
    { id = "550e8400-e29b-41d4-a716-446655440000", expected = "/tables/550e8400-e29b-41d4-a716-446655440000" },
    { id = "public.users", expected = "/tables/public.users" },
    { id = "16384_1", expected = "/tables/16384_1" },
    { id = "auth:uid", expected = "/tables/auth%3Auid" },
}

for _, case in ipairs(valid_cases) do
    reset({ id = case.id, included_schemas = "public" }, nil, '{"tableId":7}', "PATCH")
    local res, res_err = pg_meta.rewrite(context)
    assert(res == true and res_err == nil, "expected success for " .. case.id .. ", got: " .. tostring(res_err))
    assert(ngx.var.resource == case.expected, "expected " .. case.expected .. ", got: " .. tostring(ngx.var.resource))
    assert(request_state.uri_args_set.id == nil)
    assert(request_state.uri_args_set.included_schemas == "public")
    assert(request_state.body_set == '{"table_id":7}')
end

print("pg_meta rewrite runtime: ok")
