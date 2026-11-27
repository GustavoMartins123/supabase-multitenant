local cjson = require("utils.json")
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

local function storage_s3_region()
    local raw = os.getenv("STORAGE_S3_REGION")
    if type(raw) == "string" then
        local trimmed = raw:match("^%s*(.-)%s*$")
        if trimmed and trimmed ~= ""
            and #trimmed <= 63
            and trimmed:match("^[A-Za-z0-9][A-Za-z0-9%-]*$")
        then
            return trimmed:lower()
        end
    end
    return "us-east-1"
end

local function is_ident_char(ch)
    return ch ~= nil and ch ~= "" and ch:match("^[A-Za-z0-9_]$") ~= nil
end

local function skip_ws_and_comments(sql, pos)
    local n = #sql
    while pos <= n do
        local ch = sql:sub(pos, pos)
        local nxt = sql:sub(pos + 1, pos + 1)
        if ch:match("%s") then
            pos = pos + 1
        elseif ch == "-" and nxt == "-" then
            local nl = sql:find("\n", pos + 2, true)
            if not nl then
                return n + 1
            end
            pos = nl + 1
        elseif ch == "/" and nxt == "*" then
            local depth = 1
            pos = pos + 2
            while pos <= n and depth > 0 do
                local c = sql:sub(pos, pos)
                local cn = sql:sub(pos + 1, pos + 1)
                if c == "/" and cn == "*" then
                    depth = depth + 1
                    pos = pos + 2
                elseif c == "*" and cn == "/" then
                    depth = depth - 1
                    pos = pos + 2
                else
                    pos = pos + 1
                end
            end
            if depth > 0 then
                return nil
            end
        else
            break
        end
    end
    return pos
end

local function skip_single_quoted(sql, pos, escape_backslash)
    local n = #sql
    pos = pos + 1
    while pos <= n do
        local ch = sql:sub(pos, pos)
        if escape_backslash and ch == "\\" and pos < n then
            pos = pos + 2
        elseif ch == "'" then
            if sql:sub(pos + 1, pos + 1) == "'" then
                pos = pos + 2
            else
                return pos + 1
            end
        else
            pos = pos + 1
        end
    end
    return nil
end

local function skip_double_quoted(sql, pos)
    local n = #sql
    pos = pos + 1
    while pos <= n do
        local ch = sql:sub(pos, pos)
        if ch == '"' then
            if sql:sub(pos + 1, pos + 1) == '"' then
                pos = pos + 2
            else
                return pos + 1
            end
        else
            pos = pos + 1
        end
    end
    return nil
end

local function decode_sql_string_literal(raw)
    if type(raw) ~= "string" then
        return nil
    end
    local trimmed = raw:match("^%s*(.-)%s*$")
    local n = #trimmed
    if n < 2 then
        return nil
    end

    local escape_backslash = false
    local quote_pos = 1
    local first = trimmed:sub(1, 1)
    if (first == "E" or first == "e") and trimmed:sub(2, 2) == "'" then
        escape_backslash = true
        quote_pos = 2
    elseif first ~= "'" then
        return nil
    end

    local after = skip_single_quoted(trimmed, quote_pos, escape_backslash)
    if after ~= n + 1 then
        return nil
    end

    local out = {}
    local i = quote_pos + 1
    local last = n - 1
    while i <= last do
        local ch = trimmed:sub(i, i)
        if escape_backslash and ch == "\\" and i < last then
            local esc = trimmed:sub(i + 1, i + 1)
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
        elseif ch == "'" and i < last and trimmed:sub(i + 1, i + 1) == "'" then
            out[#out + 1] = "'"
            i = i + 2
        else
            out[#out + 1] = ch
            i = i + 1
        end
    end
    return table.concat(out), escape_backslash
end

local function find_execute_format_calls(sql)
    local calls = {}
    local n = #sql
    local i = 1
    while i <= n do
        local ch = sql:sub(i, i)
        local nxt = sql:sub(i + 1, i + 1)
        if (ch == "-" and nxt == "-") or (ch == "/" and nxt == "*") then
            local next_pos = skip_ws_and_comments(sql, i)
            if not next_pos then
                return nil, "Unterminated SQL comment in S3 Vectors Wrapper SQL"
            end
            i = next_pos
        elseif (ch == "E" or ch == "e") and nxt == "'"
            and (i == 1 or not is_ident_char(sql:sub(i - 1, i - 1)))
        then
            local next_pos = skip_single_quoted(sql, i + 1, true)
            if not next_pos then
                return nil, "Unterminated SQL string in S3 Vectors Wrapper SQL"
            end
            i = next_pos
        elseif ch == "'" then
            local next_pos = skip_single_quoted(sql, i, false)
            if not next_pos then
                return nil, "Unterminated SQL string in S3 Vectors Wrapper SQL"
            end
            i = next_pos
        elseif ch == '"' then
            local next_pos = skip_double_quoted(sql, i)
            if not next_pos then
                return nil, "Unterminated SQL identifier in S3 Vectors Wrapper SQL"
            end
            i = next_pos
        elseif ch:match("[A-Za-z_]") then
            local word_start = i
            while i <= n and is_ident_char(sql:sub(i, i)) do
                i = i + 1
            end
            local word = sql:sub(word_start, i - 1):lower()
            if word == "execute" then
                local pos = skip_ws_and_comments(sql, i)
                if not pos then
                    return nil, "Unterminated SQL comment in S3 Vectors Wrapper SQL"
                end
                if pos <= n and sql:sub(pos, pos):match("[A-Za-z_]") then
                    local fn_start = pos
                    while pos <= n and is_ident_char(sql:sub(pos, pos)) do
                        pos = pos + 1
                    end
                    if sql:sub(fn_start, pos - 1):lower() == "format" then
                        local open_pos = skip_ws_and_comments(sql, pos)
                        if not open_pos then
                            return nil, "Unterminated SQL comment in S3 Vectors Wrapper SQL"
                        end
                        if open_pos <= n and sql:sub(open_pos, open_pos) == "(" then
                            local cur = open_pos + 1
                            local depth = 1
                            while cur <= n and depth > 0 do
                                local c = sql:sub(cur, cur)
                                local cn = sql:sub(cur + 1, cur + 1)
                                if (c == "-" and cn == "-") or (c == "/" and cn == "*") then
                                    local next_cur = skip_ws_and_comments(sql, cur)
                                    if not next_cur then
                                        return nil, "Unterminated SQL comment in S3 Vectors Wrapper SQL"
                                    end
                                    cur = next_cur
                                elseif (c == "E" or c == "e") and cn == "'"
                                    and (cur == 1 or not is_ident_char(sql:sub(cur - 1, cur - 1)))
                                then
                                    local next_cur = skip_single_quoted(sql, cur + 1, true)
                                    if not next_cur then
                                        return nil, "Unterminated SQL string in execute format()"
                                    end
                                    cur = next_cur
                                elseif c == "'" then
                                    local next_cur = skip_single_quoted(sql, cur, false)
                                    if not next_cur then
                                        return nil, "Unterminated SQL string in execute format()"
                                    end
                                    cur = next_cur
                                elseif c == '"' then
                                    local next_cur = skip_double_quoted(sql, cur)
                                    if not next_cur then
                                        return nil, "Unterminated SQL identifier in execute format()"
                                    end
                                    cur = next_cur
                                elseif c == "(" then
                                    depth = depth + 1
                                    cur = cur + 1
                                elseif c == ")" then
                                    depth = depth - 1
                                    if depth == 0 then
                                        calls[#calls + 1] = {
                                            start_pos = word_start,
                                            end_pos = cur,
                                            args_start = open_pos + 1,
                                            args_end = cur - 1,
                                            args_str = sql:sub(open_pos + 1, cur - 1),
                                            raw = sql:sub(word_start, cur),
                                        }
                                        i = cur + 1
                                    else
                                        cur = cur + 1
                                    end
                                else
                                    cur = cur + 1
                                end
                            end
                            if depth > 0 then
                                return nil, "Unterminated execute format() in S3 Vectors Wrapper SQL"
                            end
                        end
                    end
                end
            end
        else
            i = i + 1
        end
    end
    return calls
end

local function split_sql_call_args(args_str)
    local args = {}
    local n = #args_str
    local i = 1
    local seg_start = 1
    local depth = 0

    local function push_segment(seg_end)
        local raw = args_str:sub(seg_start, seg_end)
        local leading = raw:match("^(%s*)") or ""
        local trailing = raw:match("(%s*)$") or ""
        local trim_start = seg_start + #leading
        local trim_end = seg_end - #trailing
        local trimmed = trim_start <= trim_end and args_str:sub(trim_start, trim_end) or ""
        args[#args + 1] = {
            raw = raw,
            trim_start = trim_start,
            trim_end = trim_end,
            trimmed = trimmed,
        }
    end

    while i <= n do
        local c = args_str:sub(i, i)
        local cn = args_str:sub(i + 1, i + 1)
        if (c == "-" and cn == "-") or (c == "/" and cn == "*") then
            local next_i = skip_ws_and_comments(args_str, i)
            if not next_i then
                return nil, "Unterminated SQL comment in execute format()"
            end
            i = next_i
        elseif (c == "E" or c == "e") and cn == "'"
            and (i == 1 or not is_ident_char(args_str:sub(i - 1, i - 1)))
        then
            local next_i = skip_single_quoted(args_str, i + 1, true)
            if not next_i then
                return nil, "Unterminated SQL string in execute format()"
            end
            i = next_i
        elseif c == "'" then
            local next_i = skip_single_quoted(args_str, i, false)
            if not next_i then
                return nil, "Unterminated SQL string in execute format()"
            end
            i = next_i
        elseif c == '"' then
            local next_i = skip_double_quoted(args_str, i)
            if not next_i then
                return nil, "Unterminated SQL identifier in execute format()"
            end
            i = next_i
        elseif c == "(" then
            depth = depth + 1
            i = i + 1
        elseif c == ")" then
            depth = depth - 1
            i = i + 1
        elseif c == "," and depth == 0 then
            push_segment(i - 1)
            seg_start = i + 1
            i = i + 1
        else
            i = i + 1
        end
    end
    push_segment(n)
    return args
end

local function trailing_standalone_ident(prefix)
    local trimmed = prefix:gsub("%s+$", "")
    local before, ident = trimmed:match("^(.-)([A-Za-z_][A-Za-z0-9_]*)$")
    if not ident then
        return nil
    end
    if before ~= "" then
        local prev = before:sub(-1)
        if is_ident_char(prev) or prev == "." then
            return nil
        end
    end
    return ident:lower()
end

local function preceding_option_name(template, placeholder_pos, spec)
    local prefix = template:sub(1, placeholder_pos - 1)
    if spec == "L" then
        return trailing_standalone_ident(prefix)
    end
    if spec == "s" then
        if prefix:sub(-1) ~= "'" or template:sub(placeholder_pos + 2, placeholder_pos + 2) ~= "'" then
            return nil
        end
        return trailing_standalone_ident(prefix:sub(1, -2))
    end
    return nil
end

local function is_safe_replaceable_format_arg(trimmed)
    if decode_sql_string_literal(trimmed) ~= nil then
        return true
    end
    return trimmed:match("^[A-Za-z_][A-Za-z0-9_]*$") ~= nil
end

local function replace_static_option(segment, option_name, replacement_value)
    local target = option_name:lower()
    local out = {}
    local replacements = 0
    local n = #segment
    local i = 1
    local last_emit = 1

    while i <= n do
        local ch = segment:sub(i, i)
        local nxt = segment:sub(i + 1, i + 1)
        if (ch == "-" and nxt == "-") or (ch == "/" and nxt == "*") then
            local next_i = skip_ws_and_comments(segment, i)
            if not next_i then
                break
            end
            i = next_i
        elseif (ch == "E" or ch == "e") and nxt == "'"
            and (i == 1 or not is_ident_char(segment:sub(i - 1, i - 1)))
        then
            local next_i = skip_single_quoted(segment, i + 1, true)
            if not next_i then
                break
            end
            i = next_i
        elseif ch == "'" then
            local next_i = skip_single_quoted(segment, i, false)
            if not next_i then
                break
            end
            i = next_i
        elseif ch == '"' then
            local next_i = skip_double_quoted(segment, i)
            if not next_i then
                break
            end
            i = next_i
        elseif ch:match("[A-Za-z_]") then
            local word_start = i
            while i <= n and is_ident_char(segment:sub(i, i)) do
                i = i + 1
            end
            if segment:sub(word_start, i - 1):lower() == target then
                local ws_start = i
                local after_ws = i
                while after_ws <= n and segment:sub(after_ws, after_ws):match("%s") do
                    after_ws = after_ws + 1
                end
                if after_ws > ws_start and segment:sub(after_ws, after_ws) == "'" then
                    local after_lit = skip_single_quoted(segment, after_ws, false)
                    if after_lit then
                        out[#out + 1] = segment:sub(last_emit, after_ws - 1)
                        out[#out + 1] = "'" .. replacement_value .. "'"
                        last_emit = after_lit
                        replacements = replacements + 1
                        i = after_lit
                    end
                end
            end
        else
            i = i + 1
        end
    end

    out[#out + 1] = segment:sub(last_emit)
    return table.concat(out), replacements
end

local function patch_execute_format_call(call, endpoint, region)
    local args, split_err = split_sql_call_args(call.args_str)
    if not args then
        return nil, split_err
    end
    if #args < 1 or args[1].trimmed == "" then
        return nil, "Invalid execute format() in S3 Vectors Wrapper SQL"
    end

    local template = decode_sql_string_literal(args[1].trimmed)
    if not template then
        return nil, "execute format() template must be a string literal"
    end

    local template_lower = template:lower()
    if not template_lower:find("endpoint_url", 1, true)
        and not template_lower:find("create%s+server")
        and not template_lower:find("alter%s+server")
    then
        return call.raw, 0
    end

    local replacements_by_arg = {}
    local endpoint_replacements = 0
    local arg_idx = 0
    local p = 1
    local tlen = #template

    while p <= tlen do
        if template:sub(p, p) == "%" then
            local nxt = template:sub(p + 1, p + 1)
            if nxt == "%" then
                p = p + 2
            elseif nxt == "s" or nxt == "L" or nxt == "I" then
                arg_idx = arg_idx + 1
                local option = preceding_option_name(template, p, nxt)
                if option == "endpoint_url" or option == "aws_region" then
                    local call_arg = args[arg_idx + 1]
                    if not call_arg or not is_safe_replaceable_format_arg(call_arg.trimmed) then
                        return nil, "Invalid S3 Vectors Wrapper format() argument for " .. option
                    end
                    if option == "endpoint_url" then
                        replacements_by_arg[arg_idx + 1] = "'" .. endpoint .. "'"
                        endpoint_replacements = endpoint_replacements + 1
                    else
                        replacements_by_arg[arg_idx + 1] = "'" .. region .. "'"
                    end
                end
                p = p + 2
            else
                return nil, "Unsupported format specifier in S3 Vectors Wrapper SQL"
            end
        else
            p = p + 1
        end
    end

    if arg_idx ~= (#args - 1) then
        return nil, "S3 Vectors Wrapper execute format() argument count mismatch"
    end

    local patched_args = call.args_str
    for idx = #args, 2, -1 do
        local replacement = replacements_by_arg[idx]
        if replacement then
            local arg = args[idx]
            patched_args = patched_args:sub(1, arg.trim_start - 1)
                .. replacement
                .. patched_args:sub(arg.trim_end + 1)
        end
    end

    local prefix = call.raw:sub(1, call.args_start - call.start_pos)
    local suffix = call.raw:sub(call.args_end - call.start_pos + 2)
    return prefix .. patched_args .. suffix, endpoint_replacements
end

local function count_standalone_word(sql, word)
    local lower_sql = sql:lower()
    local target = word:lower()
    local count = 0
    local pos = 1
    while true do
        local s, e = lower_sql:find(target, pos, true)
        if not s then
            break
        end
        local before = s > 1 and lower_sql:sub(s - 1, s - 1) or ""
        local after = e < #lower_sql and lower_sql:sub(e + 1, e + 1) or ""
        if not is_ident_char(before) and not is_ident_char(after) then
            count = count + 1
        end
        pos = e + 1
    end
    return count
end

local function is_canonical_uuid(value)
    if type(value) ~= "string" or #value ~= 36 then
        return false
    end
    return value:match(
        "^%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x$"
    ) ~= nil and value == value:lower()
end

-- O wrapper assina o Host do endpoint. O proxy interno dedicado valida o
-- SigV4, fixa o tenant UUID em X-Forwarded-Host e encaminha ao Storage global.
-- O patch e limitado ao SQL de criacao do S3 Vectors Wrapper.
local function patch_s3_vectors_wrapper_query(body, context)
    if type(body) ~= "table" or type(body.query) ~= "string" then
        return body
    end

    local query = body.query
    local lower_query = query:lower()
    if not lower_query:find("s3_vectors_fdw_handler", 1, true)
        or not lower_query:find("s3_vectors_fdw_validator", 1, true)
    then
        return body
    end

    local tenant_uuid = context.tenant_uuid
    if not is_canonical_uuid(tenant_uuid) then
        return nil, "Canonical tenant UUID is required for the S3 Vectors Wrapper"
    end

    local endpoint = "http://storage-vector-proxy:8081/fdw/" .. tenant_uuid .. "/vector"
    local region = storage_s3_region()

    local calls, scan_err = find_execute_format_calls(query)
    if not calls then
        return nil, scan_err
    end

    local chunks = {}
    local cursor = 1
    local total_endpoint_replacements = 0

    for _, call in ipairs(calls) do
        local before = query:sub(cursor, call.start_pos - 1)
        local before_ep, ep_count = replace_static_option(before, "endpoint_url", endpoint)
        local before_patched = replace_static_option(before_ep, "aws_region", region)
        chunks[#chunks + 1] = before_patched
        total_endpoint_replacements = total_endpoint_replacements + ep_count

        local patched_call, call_ep_count = patch_execute_format_call(call, endpoint, region)
        if not patched_call then
            return nil, call_ep_count
        end
        chunks[#chunks + 1] = patched_call
        total_endpoint_replacements = total_endpoint_replacements + call_ep_count
        cursor = call.end_pos + 1
    end

    local tail = query:sub(cursor)
    local tail_ep, tail_ep_count = replace_static_option(tail, "endpoint_url", endpoint)
    local tail_patched = replace_static_option(tail_ep, "aws_region", region)
    chunks[#chunks + 1] = tail_patched
    total_endpoint_replacements = total_endpoint_replacements + tail_ep_count

    local patched = table.concat(chunks)
    if total_endpoint_replacements ~= 1 or count_standalone_word(patched, "endpoint_url") ~= 1 then
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
    if args_err == "truncated" then
        return nil, "Too many pg-meta query parameters"
    elseif args_err then
        return nil, "Invalid pg-meta query parameters"
    end
    local id = args.id
    if id ~= nil then
        if type(id) ~= "string"
            or #id == 0
            or #id > 128
            or id == "."
            or id == ".."
            or id:find("..", 1, true) ~= nil
            or not id:match("^[A-Za-z0-9_.:%-]+$")
        then
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
