package.path = "studio/nginx/lua/?.lua;studio/nginx/lua/?/init.lua;" .. package.path

if not pcall(require, "cjson.safe") then
    local function make_cjson()
        local function decode_json_string(raw, start_pos)
            local out = {}
            local i = start_pos + 1
            local n = #raw
            while i <= n do
                local ch = raw:sub(i, i)
                if ch == "\\" and i < n then
                    local esc = raw:sub(i + 1, i + 1)
                    if esc == "n" then
                        out[#out + 1] = "\n"
                    elseif esc == "r" then
                        out[#out + 1] = "\r"
                    elseif esc == "t" then
                        out[#out + 1] = "\t"
                    else
                        out[#out + 1] = esc
                    end
                    i = i + 2
                elseif ch == '"' then
                    return table.concat(out), i + 1
                else
                    out[#out + 1] = ch
                    i = i + 1
                end
            end
            return nil
        end
        local function encode_json_string(s)
            return '"' .. s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t") .. '"'
        end
        local inst = {
            array_mt = {},
            decode_array_with_array_mt = function() end,
            encode_empty_table_as_object = function() end,
            encode_escape_forward_slash = function() return true end,
            decode = function(raw)
                if raw == '{"tableId":7}' then
                    return { tableId = 7 }
                end
                local q_start = raw:match('^%s*{%s*"query"%s*:%s*()')
                if q_start and raw:sub(q_start, q_start) == '"' then
                    local value, after = decode_json_string(raw, q_start)
                    if value and raw:sub(after):match("^%s*}%s*$") then
                        return { query = value }
                    end
                end
                return nil, "invalid json"
            end,
            encode = function(tbl)
                if type(tbl) == "table" and tbl.table_id == 7 and tbl.tableId == nil then
                    return '{"table_id":7}'
                end
                if type(tbl) == "table" and type(tbl.query) == "string" then
                    return '{"query":' .. encode_json_string(tbl.query) .. "}"
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

local json_codec = require("utils.json")
local expected_region = os.getenv("STORAGE_S3_REGION")
if not expected_region or expected_region:match("^%s*$") then
    expected_region = "us-east-1"
else
    expected_region = expected_region:match("^%s*(.-)%s*$"):lower()
end
local expected_endpoint = "http://supabase-nginx-alpha_proj:8081/vector"

-- 4. Static OPTIONS (endpoint_url '...' and optional aws_region '...')
local static_sql = "CREATE FOREIGN DATA WRAPPER my_fdw HANDLER s3_vectors_fdw_handler "
    .. "VALIDATOR s3_vectors_fdw_validator; "
    .. "CREATE SERVER my_srv FOREIGN DATA WRAPPER my_fdw "
    .. "OPTIONS (aws_region 'local', endpoint_url 'https://evil.example/vector');"
reset({}, nil, json_codec.encode({ query = static_sql }), "POST")
ngx.var.resource = "/query"
ngx.var.request_uri = "/api/platform/pg-meta/" .. REF .. "/query"
local static_ok, static_err = pg_meta.rewrite(context)
assert(static_ok == true and static_err == nil, "static wrapper rewrite failed: " .. tostring(static_err))
local static_decoded = assert(json_codec.decode(request_state.body_set))
assert(static_decoded.query:find("endpoint_url '" .. expected_endpoint .. "'", 1, true), static_decoded.query)
assert(static_decoded.query:find("aws_region '" .. expected_region .. "'", 1, true), static_decoded.query)
assert(not static_decoded.query:find("evil.example", 1, true))
assert(not static_decoded.query:find("'local'", 1, true))

-- 5. Real Studio v19/v20 DO $$ execute format(...) with supabase_target_schema
local studio_v20_sql = [[begin;
drop foreign data wrapper if exists my_docs_fdw cascade;
create foreign data wrapper my_docs_fdw
handler s3_vectors_fdw_handler
validator s3_vectors_fdw_validator;
do $$
declare
  v_vault_access_key_id text;
  v_vault_secret_access_key text;
begin
  select id into v_vault_access_key_id from vault.secrets where name = 'my_docs_fdw_vault_access_key_id' limit 1;
  select id into v_vault_secret_access_key from vault.secrets where name = 'my_docs_fdw_vault_secret_access_key' limit 1;
  execute format(
    E'create server my_docs_fdw_server foreign data wrapper my_docs_fdw options (vault_access_key_id ''%s'',vault_secret_access_key ''%s'',aws_region %L,endpoint_url %L,supabase_target_schema %L);',
    v_vault_access_key_id,v_vault_secret_access_key,'local','https://host.docker.internal:8000/storage/v1/vector','my_vectors'
  );
end $$;
commit;]]
reset({}, nil, json_codec.encode({ query = studio_v20_sql }), "POST")
ngx.var.resource = "/query"
ngx.var.request_uri = "/api/platform/pg-meta/" .. REF .. "/query"
local v20_ok, v20_err = pg_meta.rewrite(context)
assert(v20_ok == true and v20_err == nil, "Studio v20 DO execute format rewrite failed: " .. tostring(v20_err))
local v20_decoded = assert(json_codec.decode(request_state.body_set))
assert(v20_decoded.query:find("'" .. expected_endpoint .. "'", 1, true), v20_decoded.query)
assert(v20_decoded.query:find("'" .. expected_region .. "'", 1, true), v20_decoded.query)
assert(v20_decoded.query:find("'my_vectors'", 1, true), v20_decoded.query)
assert(v20_decoded.query:find("v_vault_access_key_id,v_vault_secret_access_key", 1, true), v20_decoded.query)
assert(not v20_decoded.query:find("host.docker.internal", 1, true))
assert(not v20_decoded.query:find("'local'", 1, true))

-- 6. Real Studio v19/v20 DO $$ execute format(...) without supabase_target_schema
local studio_v19_sql = [[begin;
create foreign data wrapper my_docs_fdw
handler s3_vectors_fdw_handler
validator s3_vectors_fdw_validator;
do $$
begin
  execute format(
    E'create server my_docs_fdw_server foreign data wrapper my_docs_fdw options (vault_access_key_id ''%s'',vault_secret_access_key ''%s'',aws_region %L,endpoint_url %L);',
    v_ak,v_sk,'local','https://untrusted.example/storage/v1/vector'
  );
end $$;
commit;]]
reset({}, nil, json_codec.encode({ query = studio_v19_sql }), "POST")
ngx.var.resource = "/query"
ngx.var.request_uri = "/api/platform/pg-meta/" .. REF .. "/query"
local v19_ok, v19_err = pg_meta.rewrite(context)
assert(v19_ok == true and v19_err == nil, "Studio v19 DO execute format rewrite failed: " .. tostring(v19_err))
local v19_decoded = assert(json_codec.decode(request_state.body_set))
assert(v19_decoded.query:find("'" .. expected_endpoint .. "'", 1, true), v19_decoded.query)
assert(v19_decoded.query:find("'" .. expected_region .. "'", 1, true), v19_decoded.query)
assert(not v19_decoded.query:find("untrusted.example", 1, true))

-- 7. Rejects malformed, duplicate, missing, or unsafe execute format() queries
local invalid_wrapper_queries = {
    "CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator;",
    "CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator "
        .. "OPTIONS (endpoint_url 'http://a', endpoint_url 'http://b');",
    "CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator; "
        .. "DO $$ BEGIN EXECUTE format(E'create server s foreign data wrapper f options (endpoint_url %L);', pg_read_file('/etc/passwd')); END $$;",
    "CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator; "
        .. "DO $$ BEGIN EXECUTE format(E'create server s foreign data wrapper f options (endpoint_url %L, endpoint_url %L);', 'http://a', 'http://b'); END $$;",
    "CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator; "
        .. "DO $$ BEGIN EXECUTE format(E'create server s foreign data wrapper f options (endpoint_url %L);'); END $$;",
    "CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator; "
        .. "DO $$ BEGIN EXECUTE format(E'create server s foreign data wrapper f options (endpoint_url ''http://evil/%s'');', 'x'); END $$;",
}
for _, bad_sql in ipairs(invalid_wrapper_queries) do
    reset({}, nil, json_codec.encode({ query = bad_sql }), "POST")
    ngx.var.resource = "/query"
    ngx.var.request_uri = "/api/platform/pg-meta/" .. REF .. "/query"
    local bad_ok, bad_err = pg_meta.rewrite(context)
    assert(bad_ok == nil and type(bad_err) == "string", "expected rejection for: " .. bad_sql)
end

print("pg_meta rewrite runtime: ok")
