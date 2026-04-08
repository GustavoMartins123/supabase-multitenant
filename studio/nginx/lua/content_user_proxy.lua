local bit = require("bit")
local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local http = require("resty.http")
local sha256 = require("resty.sha256")
local str = require("resty.string")

local _M = {}

local STUDIO_BASE_URL = "http://studio:3000"
local id_map_cache = ngx.shared.service_keys

local function json_array(items)
    local arr = items or {}
    return setmetatable(arr, cjson.array_mt)
end

local function trim_lower(value)
    return (value or ""):lower():gsub("%s+", "")
end

local function get_user_hash()
    local email = ngx.var.authelia_email or ""
    if email == "" then
        return nil, "authelia_email unavailable"
    end

    local h = sha256:new()
    h:update(trim_lower(email))
    return str.to_hex(h:final())
end

local function get_project_ref()
    return ngx.var.uri:match("^/api/platform/projects/([^/]+)/content")
end

local function read_body()
    ngx.req.read_body()

    local body = ngx.req.get_body_data()
    if body then
        return body
    end

    local body_file = ngx.req.get_body_file()
    if not body_file then
        return nil
    end

    local file, err = io.open(body_file, "rb")
    if not file then
        return nil, err
    end

    local data = file:read("*a")
    file:close()
    return data
end

local function request_headers(extra_headers)
    local incoming = ngx.req.get_headers()
    local headers = {
        ["Accept"] = incoming["accept"] or "application/json",
        ["Authorization"] = incoming["authorization"],
        ["Content-Type"] = incoming["content-type"],
        ["Cookie"] = incoming["cookie"],
        ["X-Forwarded-For"] = incoming["x-forwarded-for"] or ngx.var.remote_addr,
        ["X-Forwarded-Host"] = ngx.var.host,
        ["X-Forwarded-Proto"] = ngx.var.scheme,
        ["X-Real-IP"] = ngx.var.remote_addr,
    }

    if extra_headers then
        for key, value in pairs(extra_headers) do
            headers[key] = value
        end
    end

    for key, value in pairs(headers) do
        if value == nil or value == "" then
            headers[key] = nil
        end
    end

    return headers
end

local function studio_request(method, path, opts)
    opts = opts or {}

    local httpc = http.new()
    httpc:set_timeout(10000)

    local request_path = path
    if opts.query and next(opts.query) ~= nil then
        request_path = request_path .. "?" .. ngx.encode_args(opts.query)
    end

    return httpc:request_uri(STUDIO_BASE_URL .. request_path, {
        method = method,
        body = opts.body,
        headers = request_headers(opts.headers),
        keepalive = false,
    })
end

local function respond_json(status, payload)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say(cjson.encode(payload))
    return ngx.exit(status)
end

local function respond_from_studio(res)
    ngx.status = res.status

    local content_type = res.headers["Content-Type"] or res.headers["content-type"]
    if content_type then
        ngx.header["Content-Type"] = content_type
    else
        ngx.header["Content-Type"] = "application/json; charset=utf-8"
    end

    local cache_control = res.headers["Cache-Control"] or res.headers["cache-control"]
    if cache_control then
        ngx.header["Cache-Control"] = cache_control
    end

    local set_cookie = res.headers["Set-Cookie"] or res.headers["set-cookie"]
    if set_cookie then
        ngx.header["Set-Cookie"] = set_cookie
    end

    if res.body and res.body ~= "" then
        ngx.print(res.body)
    end
    return ngx.exit(res.status)
end

local function passthrough_current_request(path_override, query_override, body_override)
    local path = path_override or ngx.var.uri
    local query = query_override or ngx.req.get_uri_args()
    local body = body_override
    if body == nil and ngx.req.get_method() ~= "GET" and ngx.req.get_method() ~= "HEAD" then
        body = read_body()
    end

    local res, err = studio_request(ngx.req.get_method(), path, {
        query = query,
        body = body,
    })

    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Studio passthrough failed: ", err or "unknown error")
        return respond_json(502, { error = { message = "Studio proxy request failed" } })
    end

    return respond_from_studio(res)
end

local function simple_hash(input)
    local hash = 0
    for i = 1, #input do
        local code = input:byte(i)
        hash = bit.tobit(bit.lshift(hash, 5) - hash + code)
    end

    if hash == -2147483648 then
        return 2147483648
    end

    if hash < 0 then
        return -hash
    end

    return hash
end

local function deterministic_uuid(inputs)
    local cleaned = {}
    for _, value in ipairs(inputs or {}) do
        if value and value ~= "" then
            table.insert(cleaned, tostring(value))
        end
    end

    local seed = simple_hash(table.concat(cleaned, "_"))
    local bytes = {}

    for i = 1, 16 do
        -- Intentionally use Lua number arithmetic here so the LCG matches
        -- the Studio's JavaScript implementation, including floating-point
        -- precision loss before the 32-bit bitwise mask.
        seed = bit.band(seed * 1103515245 + 12345, 0x7fffffff)
        bytes[i] = bit.band(bit.rshift(seed, 16), 0xff)
    end

    bytes[7] = bit.bor(bit.band(bytes[7], 0x0f), 0x40)
    bytes[9] = bit.bor(bit.band(bytes[9], 0x3f), 0x80)

    local parts = {}
    for i = 1, 16 do
        parts[i] = string.format("%02x", bytes[i])
    end

    return table.concat({
        table.concat(parts, "", 1, 4),
        table.concat(parts, "", 5, 6),
        table.concat(parts, "", 7, 8),
        table.concat(parts, "", 9, 10),
        table.concat(parts, "", 11, 16),
    }, "-")
end

local function virtual_snippet_id(name)
    return deterministic_uuid({ string.format("%s.sql", name) })
end

local function actual_folder_id(user_hash)
    return deterministic_uuid({ user_hash })
end

local function actual_snippet_id(folder_id, name)
    return deterministic_uuid({ folder_id, string.format("%s.sql", name) })
end

local function snippet_map_key(project_ref, user_hash, request_id)
    return table.concat({
        "snippet-id-map",
        project_ref or "",
        user_hash or "",
        request_id or "",
    }, ":")
end

local function actual_map_key(project_ref, user_hash, actual_id)
    return table.concat({
        "snippet-actual-map",
        project_ref or "",
        user_hash or "",
        actual_id or "",
    }, ":")
end

local function get_mapped_actual_id(project_ref, user_hash, request_id)
    if not id_map_cache or not project_ref or not user_hash or not request_id or request_id == "" then
        return nil
    end

    return id_map_cache:get(snippet_map_key(project_ref, user_hash, request_id))
end

local function get_preferred_virtual_id(project_ref, user_hash, actual_id)
    if not id_map_cache or not project_ref or not user_hash or not actual_id or actual_id == "" then
        return nil
    end

    return id_map_cache:get(actual_map_key(project_ref, user_hash, actual_id))
end

local function set_mapped_actual_id(project_ref, user_hash, request_id, actual_id, remember_as_preferred)
    if not id_map_cache or not project_ref or not user_hash or not request_id or request_id == "" then
        return
    end
    if not actual_id or actual_id == "" then
        return
    end

    id_map_cache:set(snippet_map_key(project_ref, user_hash, request_id), actual_id, 86400)

    if remember_as_preferred then
        id_map_cache:set(actual_map_key(project_ref, user_hash, actual_id), request_id, 86400)
    end
end

local function clone_table(value)
    local cloned = {}
    for key, item in pairs(value or {}) do
        cloned[key] = item
    end
    return cloned
end

local function to_virtual_snippet(snippet, virtual_id)
    local cloned = clone_table(snippet)
    cloned.id = virtual_id or virtual_snippet_id(cloned.name or "")
    cloned.folder_id = cjson.null
    return cloned
end

local function resolve_virtual_snippet_id(project_ref, user_hash, snippet)
    if type(snippet) ~= "table" or not snippet.id or snippet.id == "" then
        return nil
    end

    local preferred = get_preferred_virtual_id(project_ref, user_hash, snippet.id)
    if preferred and preferred ~= "" then
        set_mapped_actual_id(project_ref, user_hash, preferred, snippet.id, true)
        return preferred
    end

    local canonical = virtual_snippet_id(snippet.name or "")
    set_mapped_actual_id(project_ref, user_hash, canonical, snippet.id, false)
    return canonical
end

local function map_actual_cursor_to_virtual(actual_cursor, snippets, project_ref, user_hash)
    if not actual_cursor or actual_cursor == "" then
        return nil
    end

    for _, snippet in ipairs(snippets or {}) do
        if snippet.id == actual_cursor then
            return resolve_virtual_snippet_id(project_ref, user_hash, snippet)
        end
    end

    return nil
end

local function parse_json_response(res)
    if not res.body or res.body == "" then
        return {}
    end

    return cjson_safe.decode(res.body) or {}
end

local function find_existing_user_folder(project_ref, user_hash)
    local res, err = studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders", {
        query = {
            type = "sql",
            visibility = "user",
            limit = "1000",
            sort_by = "name",
            sort_order = "asc",
        },
    })

    if not res then
        return nil, "failed to list folders: " .. (err or "unknown error")
    end

    if res.status ~= 200 then
        return nil, "failed to list folders: status " .. tostring(res.status)
    end

    local payload = parse_json_response(res)
    local folders = (((payload or {}).data or {}).folders) or {}
    for _, folder in ipairs(folders) do
        if folder.name == user_hash then
            return folder
        end
    end

    return nil
end

local function resolve_user_folder(project_ref, create_if_missing)
    local user_hash, user_err = get_user_hash()
    if not user_hash then
        return nil, user_err
    end

    local folder, find_err = find_existing_user_folder(project_ref, user_hash)
    if folder then
        return folder
    end

    if not create_if_missing then
        return {
            id = actual_folder_id(user_hash),
            name = user_hash,
            owner_id = 1,
            parent_id = cjson.null,
            project_id = 1,
            _synthetic = true,
        }
    end

    if find_err then
        ngx.log(ngx.WARN, "[CONTENT-PROXY] Could not confirm existing folder before create: ", find_err)
    end

    local create_res, create_err = studio_request("POST", "/api/platform/projects/" .. project_ref .. "/content/folders", {
        body = cjson.encode({ name = user_hash }),
        headers = { ["Content-Type"] = "application/json" },
    })

    if not create_res then
        return nil, "failed to create folder: " .. (create_err or "unknown error")
    end

    if create_res.status == 200 or create_res.status == 201 then
        local created = parse_json_response(create_res)
        if created and created.id then
            return created
        end
    end

    folder = find_existing_user_folder(project_ref, user_hash)
    if folder then
        return folder
    end

    return nil, "failed to resolve user folder"
end

local function list_user_snippets(project_ref, folder_id)
    local res, err = studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders/" .. folder_id, {
        query = {
            limit = "1000",
            sort_by = "inserted_at",
            sort_order = "desc",
        },
    })

    if not res then
        return nil, "failed to list snippets: " .. (err or "unknown error")
    end

    if res.status ~= 200 then
        return nil, "failed to list snippets: status " .. tostring(res.status)
    end

    local payload = parse_json_response(res)
    return (((payload or {}).data or {}).contents) or {}
end

local function find_actual_snippet_by_request_id(project_ref, folder_id, user_hash, request_id)
    if not request_id or request_id == "" then
        return nil
    end

    local snippets, err = list_user_snippets(project_ref, folder_id)
    if not snippets then
        ngx.log(ngx.WARN, "[CONTENT-PROXY] Could not list user snippets: ", err or "unknown error")
        return nil
    end

    for _, snippet in ipairs(snippets) do
        local canonical_id = virtual_snippet_id(snippet.name)
        local visible_id = resolve_virtual_snippet_id(project_ref, user_hash, snippet)

        if snippet.id == request_id or canonical_id == request_id or visible_id == request_id then
            set_mapped_actual_id(project_ref, user_hash, request_id, snippet.id, visible_id == request_id)
            return snippet
        end
    end

    return nil
end

local function resolve_actual_snippet(project_ref, folder_id, user_hash, request_id)
    if not request_id or request_id == "" then
        return nil
    end

    local mapped_actual_id = get_mapped_actual_id(project_ref, user_hash, request_id)
    if mapped_actual_id and mapped_actual_id ~= "" then
        local snippets, err = list_user_snippets(project_ref, folder_id)
        if not snippets then
            ngx.log(ngx.WARN, "[CONTENT-PROXY] Could not validate cached snippet id: ", err or "unknown error")
        else
            for _, snippet in ipairs(snippets) do
                if snippet.id == mapped_actual_id then
                    return snippet
                end
            end
        end
    end

    return find_actual_snippet_by_request_id(project_ref, folder_id, user_hash, request_id)
end

local function parse_boolean(value)
    if value == nil then
        return nil
    end

    local normalized = tostring(value):lower()
    if normalized == "true" or normalized == "1" then
        return true
    end
    if normalized == "false" or normalized == "0" then
        return false
    end
    return nil
end

local function rewrite_content_list_response(actual_payload, args, project_ref, user_hash)
    local actual_contents = (((actual_payload or {}).data or {}).contents) or {}
    local virtual_contents = {}

    for _, snippet in ipairs(actual_contents) do
        table.insert(
            virtual_contents,
            to_virtual_snippet(snippet, resolve_virtual_snippet_id(project_ref, user_hash, snippet))
        )
    end

    local favorite_filter = parse_boolean(args.favorite)
    if favorite_filter ~= nil then
        local filtered = {}
        for _, snippet in ipairs(virtual_contents) do
            if snippet.favorite == favorite_filter then
                table.insert(filtered, snippet)
            end
        end
        virtual_contents = filtered
    end

    local response = {
        data = json_array(virtual_contents),
    }

    local virtual_cursor = map_actual_cursor_to_virtual(
        actual_payload.cursor,
        actual_contents,
        project_ref,
        user_hash
    )
    if virtual_cursor then
        response.cursor = virtual_cursor
    end

    return response
end

local function rewrite_folder_list_response(actual_payload, project_ref, user_hash)
    local actual_contents = (((actual_payload or {}).data or {}).contents) or {}
    local virtual_contents = {}

    for _, snippet in ipairs(actual_contents) do
        table.insert(
            virtual_contents,
            to_virtual_snippet(snippet, resolve_virtual_snippet_id(project_ref, user_hash, snippet))
        )
    end

    local response = {
        data = {
            folders = json_array({}),
            contents = json_array(virtual_contents),
        },
    }

    local virtual_cursor = map_actual_cursor_to_virtual(
        actual_payload.cursor,
        actual_contents,
        project_ref,
        user_hash
    )
    if virtual_cursor then
        response.cursor = virtual_cursor
    end

    return response
end

function _M.handle_content()
    local project_ref = get_project_ref()
    if not project_ref then
        return passthrough_current_request()
    end

    local method = ngx.req.get_method()
    local args = ngx.req.get_uri_args()

    if method == "GET" then
        if args.type ~= "sql" then
            return passthrough_current_request()
        end
        if args.visibility == "project" then
            return respond_json(200, { data = json_array({}) })
        end

        local user_hash = get_user_hash()

        local folder, folder_err = resolve_user_folder(project_ref, true)
        if not folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local upstream_args = clone_table(args)
        upstream_args.type = nil
        upstream_args.visibility = nil

        if upstream_args.cursor then
            local mapped = resolve_actual_snippet(project_ref, folder.id, user_hash, upstream_args.cursor)
            upstream_args.cursor = mapped and mapped.id or nil
        end

        local res, err = studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders/" .. folder.id, {
            query = upstream_args,
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch user content: ", err or "unknown error")
            return respond_json(502, { error = { message = "Failed to fetch snippets" } })
        end

        if res.status ~= 200 then
            return respond_from_studio(res)
        end

        return respond_json(200, rewrite_content_list_response(parse_json_response(res), args, project_ref, user_hash))
    end

    if method == "PUT" then
        local raw_body, body_err = read_body()
        if body_err then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to read request body: ", body_err)
            return respond_json(400, { error = { message = "Failed to read request body" } })
        end

        local payload = cjson_safe.decode(raw_body or "")
        if type(payload) ~= "table" or payload.type ~= "sql" then
            return passthrough_current_request(nil, nil, raw_body)
        end

        if payload.visibility == "project" then
            return passthrough_current_request(nil, nil, raw_body)
        end

        local user_hash, user_hash_err = get_user_hash()
        if not user_hash then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user identity" } })
        end

        local folder, folder_err = resolve_user_folder(project_ref, true)
        if not folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to ensure user folder: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to ensure user folder" } })
        end

        local incoming_id = payload.id
        local canonical_virtual_id = virtual_snippet_id(payload.name or "")
        local existing = resolve_actual_snippet(project_ref, folder.id, user_hash, incoming_id)
        if not existing and canonical_virtual_id ~= incoming_id then
            existing = resolve_actual_snippet(project_ref, folder.id, user_hash, canonical_virtual_id)
        end

        if existing then
            payload.id = existing.id
        else
            payload.id = canonical_virtual_id
        end

        if type(payload.content) == "table" then
            payload.content.content_id = payload.id
        end

        payload.folder_id = folder.id

        local encoded = cjson.encode(payload)
        local res, err = studio_request("PUT", "/api/platform/projects/" .. project_ref .. "/content", {
            body = encoded,
            headers = { ["Content-Type"] = "application/json" },
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to upsert snippet: ", err or "unknown error")
            return respond_json(502, { error = { message = "Failed to save snippet" } })
        end

        if res.status < 200 or res.status >= 300 then
            return respond_from_studio(res)
        end

        local saved = parse_json_response(res)
        if type(saved) == "table" and saved.name then
            set_mapped_actual_id(project_ref, user_hash, incoming_id, saved.id, true)
            set_mapped_actual_id(project_ref, user_hash, canonical_virtual_id, saved.id, false)
            saved = to_virtual_snippet(saved, incoming_id or canonical_virtual_id)
        end

        return respond_json(res.status, saved)
    end

    if method == "DELETE" then
        local ids = args.ids
        if type(ids) ~= "string" or ids == "" then
            return passthrough_current_request()
        end

        local user_hash = get_user_hash()
        local folder = resolve_user_folder(project_ref, false)
        if not folder then
            return respond_json(200, json_array({}))
        end

        local mapped_ids = {}
        local requested_ids = {}
        for id in string.gmatch(ids, "([^,]+)") do
            local trimmed = (id or ""):gsub("^%s+", ""):gsub("%s+$", "")
            if trimmed ~= "" then
                table.insert(requested_ids, trimmed)
                local actual = resolve_actual_snippet(project_ref, folder.id, user_hash, trimmed)
                if not actual then
                    return passthrough_current_request()
                end
                table.insert(mapped_ids, actual.id)
            end
        end

        local res, err = studio_request("DELETE", "/api/platform/projects/" .. project_ref .. "/content", {
            query = { ids = table.concat(mapped_ids, ",") },
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to delete snippets: ", err or "unknown error")
            return respond_json(502, { error = { message = "Failed to delete snippets" } })
        end

        if res.status < 200 or res.status >= 300 then
            return respond_from_studio(res)
        end

        local response = {}
        for _, id in ipairs(requested_ids) do
            table.insert(response, { id = id })
        end

        return respond_json(res.status, json_array(response))
    end

    return passthrough_current_request()
end

function _M.handle_folders()
    local project_ref = get_project_ref()
    if not project_ref then
        return passthrough_current_request()
    end

    local method = ngx.req.get_method()
    local args = ngx.req.get_uri_args()

    if method ~= "GET" or args.type ~= "sql" then
        return passthrough_current_request()
    end

    local user_hash = get_user_hash()

    local folder, folder_err = resolve_user_folder(project_ref, true)
    if not folder then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder for folders route: ", folder_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local upstream_args = clone_table(args)
    upstream_args.type = nil
    upstream_args.visibility = nil

    if upstream_args.cursor then
        local mapped = resolve_actual_snippet(project_ref, folder.id, user_hash, upstream_args.cursor)
        upstream_args.cursor = mapped and mapped.id or nil
    end

    local res, err = studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders/" .. folder.id, {
        query = upstream_args,
    })

    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch folder contents: ", err or "unknown error")
        return respond_json(502, { error = { message = "Failed to fetch folder contents" } })
    end

    if res.status ~= 200 then
        return respond_from_studio(res)
    end

    return respond_json(200, rewrite_folder_list_response(parse_json_response(res), project_ref, user_hash))
end

function _M.handle_count()
    local project_ref = get_project_ref()
    if not project_ref then
        return passthrough_current_request()
    end

    local args = ngx.req.get_uri_args()
    if args.type ~= "sql" then
        return passthrough_current_request()
    end

    local folder, folder_err = resolve_user_folder(project_ref, true)
    if not folder then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder for count route: ", folder_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local res, err = studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders/" .. folder.id, {
        query = {
            name = args.name,
            limit = "100",
            sort_by = "inserted_at",
            sort_order = "desc",
        },
    })

    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch snippets for count: ", err or "unknown error")
        return respond_json(502, { error = { message = "Failed to fetch snippets for count" } })
    end

    if res.status ~= 200 then
        return respond_from_studio(res)
    end

    local actual_contents = (((parse_json_response(res) or {}).data or {}).contents) or {}
    if args.name and args.name ~= "" then
        return respond_json(200, { count = #actual_contents })
    end

    local favorites = 0
    for _, snippet in ipairs(actual_contents) do
        if snippet.favorite then
            favorites = favorites + 1
        end
    end

    return respond_json(200, {
        shared = 0,
        favorites = favorites,
        private = #actual_contents,
    })
end

function _M.handle_item()
    local project_ref = get_project_ref()
    local item_id = ngx.var.uri:match("/content/item/([^/]+)$")
    if not project_ref or not item_id then
        return passthrough_current_request()
    end

    local user_hash = get_user_hash()

    local folder = resolve_user_folder(project_ref, false)
    if not folder then
        return passthrough_current_request()
    end

    local actual = resolve_actual_snippet(project_ref, folder.id, user_hash, item_id)
    if not actual or not actual.id then
        return passthrough_current_request()
    end

    local res, err = studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/item/" .. actual.id)
    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch snippet by item id: ", err or "unknown error")
        return respond_json(502, { error = { message = "Failed to fetch snippet" } })
    end

    if res.status ~= 200 then
        return respond_from_studio(res)
    end

    local payload = parse_json_response(res)
    if type(payload) == "table" and payload.name then
        payload = to_virtual_snippet(payload, item_id)
    end

    return respond_json(200, payload)
end

return _M
