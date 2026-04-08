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

local function get_project_scope()
    local project_ref = ngx.var.project_ref
    if project_ref and project_ref ~= "" then
        return project_ref
    end

    return get_project_ref() or "default"
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

local function virtual_snippet_id(name, virtual_folder_id)
    if virtual_folder_id and virtual_folder_id ~= cjson.null and virtual_folder_id ~= "" then
        return deterministic_uuid({ virtual_folder_id, string.format("%s.sql", name) })
    end

    return deterministic_uuid({ string.format("%s.sql", name) })
end

local function build_folder_name(user_hash, project_scope)
    local normalized_scope = tostring(project_scope or ""):gsub("[^%w._-]", "_")
    if normalized_scope == "" or normalized_scope == "default" then
        return user_hash
    end

    return string.format("%s__%s", user_hash, normalized_scope)
end

local function build_folder_prefix(user_hash, project_scope)
    return build_folder_name(user_hash, project_scope) .. "__"
end

local function sanitize_folder_segment(name)
    local value = tostring(name or ""):gsub("^%s+", ""):gsub("%s+$", "")
    if value == "" then
        return nil, "Folder name is required"
    end

    if value:find("%z", 1, true) or value:find("/", 1, true) or value:find("\\", 1, true) then
        return nil, "Invalid folder name"
    end

    return value
end

local function actual_child_folder_name(user_hash, project_scope, visible_name)
    return build_folder_prefix(user_hash, project_scope) .. visible_name
end

local function actual_folder_id(folder_name)
    return deterministic_uuid({ folder_name })
end

local function actual_snippet_id(folder_id, name)
    return deterministic_uuid({ folder_id, string.format("%s.sql", name) })
end

local function virtual_folder_id(user_hash, project_scope, visible_name)
    return deterministic_uuid({ build_folder_name(user_hash, project_scope), visible_name })
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

local function folder_map_key(project_ref, user_hash, request_id)
    return table.concat({
        "folder-id-map",
        project_ref or "",
        user_hash or "",
        request_id or "",
    }, ":")
end

local function folder_actual_map_key(project_ref, user_hash, actual_id)
    return table.concat({
        "folder-actual-map",
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

local function get_mapped_actual_folder_id(project_ref, user_hash, request_id)
    if not id_map_cache or not project_ref or not user_hash or not request_id or request_id == "" then
        return nil
    end

    return id_map_cache:get(folder_map_key(project_ref, user_hash, request_id))
end

local function get_preferred_virtual_folder_id(project_ref, user_hash, actual_id)
    if not id_map_cache or not project_ref or not user_hash or not actual_id or actual_id == "" then
        return nil
    end

    return id_map_cache:get(folder_actual_map_key(project_ref, user_hash, actual_id))
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

local function set_mapped_actual_folder_id(project_ref, user_hash, request_id, actual_id, remember_as_preferred)
    if not id_map_cache or not project_ref or not user_hash or not request_id or request_id == "" then
        return
    end
    if not actual_id or actual_id == "" then
        return
    end

    id_map_cache:set(folder_map_key(project_ref, user_hash, request_id), actual_id, 86400)

    if remember_as_preferred then
        id_map_cache:set(folder_actual_map_key(project_ref, user_hash, actual_id), request_id, 86400)
    end
end

local function append_unique(items, seen, value)
    if not value or value == "" or seen[value] then
        return
    end

    seen[value] = true
    table.insert(items, value)
end

local function build_folder_aliases(user_hash, project_scope, folder, visible_name)
    local aliases = {}
    local seen = {}

    append_unique(aliases, seen, virtual_folder_id(user_hash, project_scope, visible_name))
    append_unique(aliases, seen, virtual_folder_id(user_hash, "default", visible_name))
    append_unique(aliases, seen, deterministic_uuid({ visible_name }))

    if type(folder) == "table" then
        append_unique(aliases, seen, folder.id)
        append_unique(aliases, seen, deterministic_uuid({ folder.name }))
    end

    return aliases
end

local function clone_table(value)
    local cloned = {}
    for key, item in pairs(value or {}) do
        cloned[key] = item
    end
    return cloned
end

local function to_virtual_snippet(snippet, virtual_id, virtual_folder_id)
    local cloned = clone_table(snippet)
    cloned.id = virtual_id or virtual_snippet_id(cloned.name or "")
    cloned.folder_id = virtual_folder_id or cjson.null
    return cloned
end

local function resolve_virtual_snippet_id(project_ref, user_hash, snippet, virtual_folder_id)
    if type(snippet) ~= "table" or not snippet.id or snippet.id == "" then
        return nil
    end

    local preferred = get_preferred_virtual_id(project_ref, user_hash, snippet.id)
    if preferred and preferred ~= "" then
        set_mapped_actual_id(project_ref, user_hash, preferred, snippet.id, true)
        return preferred
    end

    local canonical = virtual_snippet_id(snippet.name or "", virtual_folder_id)
    set_mapped_actual_id(project_ref, user_hash, canonical, snippet.id, false)
    return canonical
end

local function parse_json_response(res)
    if not res.body or res.body == "" then
        return {}
    end

    return cjson_safe.decode(res.body) or {}
end

local function normalize_limit(value)
    local parsed = tonumber(value)
    if not parsed or parsed <= 0 then
        return 100
    end

    parsed = math.floor(parsed)
    if parsed > 1000 then
        return 1000
    end

    return parsed
end

local function normalize_sort(sort_by, sort_order)
    local resolved_sort = sort_by == "name" and "name" or "inserted_at"
    local resolved_order = sort_order == "asc" and "asc" or "desc"
    return resolved_sort, resolved_order
end

local function list_all_folders(project_ref)
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
    return (((payload or {}).data or {}).folders) or {}
end

local function load_namespace_state(project_ref, user_hash, project_scope)
    local folders, err = list_all_folders(project_ref)
    if not folders then
        return nil, err
    end

    local root_name = build_folder_name(user_hash, project_scope)
    local prefix = build_folder_prefix(user_hash, project_scope)
    local state = {
        root_name = root_name,
        prefix = prefix,
        root_folder = nil,
        child_folders = {},
        child_by_actual_id = {},
        child_by_virtual_id = {},
        child_by_visible_name = {},
    }

    for _, folder in ipairs(folders) do
        if folder.name == root_name then
            state.root_folder = folder
        elseif folder.name:sub(1, #prefix) == prefix then
            local visible_name = folder.name:sub(#prefix + 1)
            if visible_name ~= "" then
                local safe_visible_name = sanitize_folder_segment(visible_name)
                if safe_visible_name then
                    visible_name = safe_visible_name
                end

                local preferred_virtual_id = get_preferred_virtual_folder_id(project_scope, user_hash, folder.id)
                local aliases = build_folder_aliases(user_hash, project_scope, folder, visible_name)
                local canonical_virtual_id = aliases[1]
                local resolved_virtual_id = preferred_virtual_id
                if not resolved_virtual_id or resolved_virtual_id == "" then
                    resolved_virtual_id = canonical_virtual_id
                end

                set_mapped_actual_folder_id(project_scope, user_hash, canonical_virtual_id, folder.id, false)
                if resolved_virtual_id ~= canonical_virtual_id then
                    set_mapped_actual_folder_id(project_scope, user_hash, resolved_virtual_id, folder.id, true)
                end

                local virtual = {
                    id = resolved_virtual_id,
                    name = visible_name,
                    owner_id = folder.owner_id or 1,
                    parent_id = cjson.null,
                    project_id = folder.project_id or 1,
                }
                local entry = {
                    actual = folder,
                    virtual = virtual,
                    canonical_virtual_id = canonical_virtual_id,
                    aliases = aliases,
                }
                table.insert(state.child_folders, entry)
                state.child_by_actual_id[folder.id] = entry
                state.child_by_virtual_id[virtual.id] = entry
                for _, alias in ipairs(aliases) do
                    state.child_by_virtual_id[alias] = entry
                end
                state.child_by_visible_name[visible_name] = entry
            end
        end
    end

    table.sort(state.child_folders, function(a, b)
        return (a.virtual.name or ""):lower() < (b.virtual.name or ""):lower()
    end)

    return state
end

local function resolve_namespace_root_folder(project_ref, user_hash, project_scope, create_if_missing)
    local state, state_err = load_namespace_state(project_ref, user_hash, project_scope)
    if not state then
        return nil, nil, state_err
    end

    if state.root_folder then
        return state.root_folder, state
    end

    if not create_if_missing then
        local synthetic = {
            id = actual_folder_id(state.root_name),
            name = state.root_name,
            owner_id = 1,
            parent_id = cjson.null,
            project_id = 1,
            _synthetic = true,
        }
        state.root_folder = synthetic
        return synthetic, state
    end

    local create_res, create_err = studio_request("POST", "/api/platform/projects/" .. project_ref .. "/content/folders", {
        body = cjson.encode({ name = state.root_name }),
        headers = { ["Content-Type"] = "application/json" },
    })

    if not create_res then
        return nil, nil, "failed to create folder: " .. (create_err or "unknown error")
    end

    local refreshed, refreshed_err = load_namespace_state(project_ref, user_hash, project_scope)
    if refreshed and refreshed.root_folder then
        return refreshed.root_folder, refreshed
    end

    return nil, nil, refreshed_err or "failed to resolve user folder"
end

local function create_namespaced_folder(project_ref, user_hash, project_scope, visible_name)
    local safe_name, safe_err = sanitize_folder_segment(visible_name)
    if not safe_name then
        return nil, safe_err
    end

    local state, state_err = load_namespace_state(project_ref, user_hash, project_scope)
    if not state then
        return nil, state_err
    end

    if state.child_by_visible_name[safe_name] then
        return nil, "Folder already exists"
    end

    local actual_name = actual_child_folder_name(user_hash, project_scope, safe_name)
    local create_res, create_err = studio_request("POST", "/api/platform/projects/" .. project_ref .. "/content/folders", {
        body = cjson.encode({ name = actual_name }),
        headers = { ["Content-Type"] = "application/json" },
    })

    if not create_res then
        return nil, "failed to create folder: " .. (create_err or "unknown error")
    end

    local refreshed, refreshed_err = load_namespace_state(project_ref, user_hash, project_scope)
    if refreshed and refreshed.child_by_visible_name[safe_name] then
        return refreshed.child_by_visible_name[safe_name], refreshed
    end

    return nil, refreshed_err or "failed to resolve created folder"
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

local function collect_namespace_snippets(project_ref, namespace_state, opts)
    opts = opts or {}

    local snippets = {}

    local function append_from_folder(folder)
        if not folder or folder._synthetic then
            return true
        end

        local folder_snippets, folder_err = list_user_snippets(project_ref, folder.id)
        if not folder_snippets then
            return nil, folder_err
        end

        for _, snippet in ipairs(folder_snippets) do
            table.insert(snippets, snippet)
        end

        return true
    end

    if opts.actual_folder then
        local ok, folder_err = append_from_folder(opts.actual_folder)
        if not ok then
            return nil, folder_err
        end
        return snippets
    end

    if opts.include_root ~= false then
        local ok, folder_err = append_from_folder(namespace_state.root_folder)
        if not ok then
            return nil, folder_err
        end
    end

    if opts.include_children then
        for _, entry in ipairs(namespace_state.child_folders) do
            local ok, folder_err = append_from_folder(entry.actual)
            if not ok then
                return nil, folder_err
            end
        end
    end

    return snippets
end

local function resolve_virtual_folder_id_for_snippet(namespace_state, snippet)
    if type(snippet) ~= "table" then
        return nil
    end

    local actual_folder_id = snippet.folder_id
    if actual_folder_id == nil or actual_folder_id == cjson.null or actual_folder_id == "" then
        return nil
    end

    if namespace_state.root_folder and actual_folder_id == namespace_state.root_folder.id then
        return nil
    end

    local entry = namespace_state.child_by_actual_id[actual_folder_id]
    return entry and entry.virtual.id or nil
end

local function virtualize_snippet(scope_key, user_hash, namespace_state, snippet, forced_virtual_id)
    local virtual_folder = resolve_virtual_folder_id_for_snippet(namespace_state, snippet)
    local virtual_id = forced_virtual_id or resolve_virtual_snippet_id(scope_key, user_hash, snippet, virtual_folder)
    return to_virtual_snippet(snippet, virtual_id, virtual_folder)
end

local function resolve_actual_folder(scope_key, user_hash, namespace_state, requested_folder_id)
    if requested_folder_id == nil or requested_folder_id == cjson.null or requested_folder_id == "" then
        return namespace_state.root_folder
    end

    local entry = namespace_state.child_by_virtual_id[requested_folder_id]
        or namespace_state.child_by_actual_id[requested_folder_id]
    if entry then
        if user_hash and requested_folder_id ~= entry.actual.id then
            set_mapped_actual_folder_id(scope_key, user_hash, requested_folder_id, entry.actual.id, true)
        end
        return entry.actual
    end

    if user_hash then
        local mapped_actual_id = get_mapped_actual_folder_id(scope_key, user_hash, requested_folder_id)
        if mapped_actual_id and mapped_actual_id ~= "" then
            entry = namespace_state.child_by_actual_id[mapped_actual_id]
            if entry then
                set_mapped_actual_folder_id(scope_key, user_hash, requested_folder_id, entry.actual.id, true)
                return entry.actual
            end
        end
    end

    for _, folder_entry in ipairs(namespace_state.child_folders) do
        for _, alias in ipairs(folder_entry.aliases or {}) do
            if alias == requested_folder_id then
                if user_hash then
                    set_mapped_actual_folder_id(
                        scope_key,
                        user_hash,
                        requested_folder_id,
                        folder_entry.actual.id,
                        requested_folder_id ~= folder_entry.actual.id
                    )
                end
                return folder_entry.actual
            end
        end
    end

    return nil
end

local function find_actual_snippet_in_collection(scope_key, user_hash, request_id, namespace_state, snippets)
    if not request_id or request_id == "" then
        return nil
    end

    local mapped_actual_id = get_mapped_actual_id(scope_key, user_hash, request_id)
    if mapped_actual_id and mapped_actual_id ~= "" then
        for _, snippet in ipairs(snippets or {}) do
            if snippet.id == mapped_actual_id then
                return snippet
            end
        end
    end

    for _, snippet in ipairs(snippets or {}) do
        local virtual_folder = resolve_virtual_folder_id_for_snippet(namespace_state, snippet)
        local canonical_id = virtual_snippet_id(snippet.name, virtual_folder)
        local visible_id = resolve_virtual_snippet_id(scope_key, user_hash, snippet, virtual_folder)

        if snippet.id == request_id or canonical_id == request_id or visible_id == request_id then
            set_mapped_actual_id(scope_key, user_hash, request_id, snippet.id, visible_id == request_id)
            return snippet
        end
    end

    return nil
end

local function resolve_actual_snippet(project_ref, namespace_state, scope_key, user_hash, request_id, actual_folder)
    if not request_id or request_id == "" then
        return nil
    end

    local snippets, err = collect_namespace_snippets(
        project_ref,
        namespace_state,
        actual_folder and { actual_folder = actual_folder } or { include_root = true, include_children = true }
    )
    if not snippets then
        ngx.log(ngx.WARN, "[CONTENT-PROXY] Could not list namespace snippets: ", err or "unknown error")
        return nil
    end

    return find_actual_snippet_in_collection(scope_key, user_hash, request_id, namespace_state, snippets)
end

local function build_virtual_folder_array(namespace_state)
    local folders = {}
    for _, entry in ipairs(namespace_state.child_folders) do
        table.insert(folders, clone_table(entry.virtual))
    end
    return folders
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

local function build_virtual_snippet_page(raw_snippets, args, scope_key, user_hash, namespace_state)
    local favorite_filter = parse_boolean(args.favorite)
    local search_term = tostring(args.name or ""):lower()
    local items = {}

    for _, snippet in ipairs(raw_snippets or {}) do
        local virtual = virtualize_snippet(scope_key, user_hash, namespace_state, snippet)
        local matches_search =
            search_term == ""
            or ((virtual.name or ""):lower():find(search_term, 1, true) ~= nil)
        local matches_favorite = favorite_filter == nil or virtual.favorite == favorite_filter

        if matches_search and matches_favorite then
            table.insert(items, virtual)
        end
    end

    local sort_by, sort_order = normalize_sort(args.sort_by, args.sort_order)
    table.sort(items, function(a, b)
        local a_key
        local b_key

        if sort_by == "name" then
            a_key = (a.name or ""):lower()
            b_key = (b.name or ""):lower()
        else
            a_key = a.inserted_at or ""
            b_key = b.inserted_at or ""
        end

        if a_key == b_key then
            if sort_order == "asc" then
                return (a.id or "") < (b.id or "")
            end
            return (a.id or "") > (b.id or "")
        end

        if sort_order == "asc" then
            return a_key < b_key
        end
        return a_key > b_key
    end)

    local start_index = 1
    if args.cursor and args.cursor ~= "" then
        for index, item in ipairs(items) do
            if item.id == args.cursor then
                start_index = index + 1
                break
            end
        end
    end

    local limit = normalize_limit(args.limit)
    local page = {}
    local last_index = math.min(#items, start_index + limit - 1)

    for index = start_index, last_index do
        if items[index] then
            table.insert(page, items[index])
        end
    end

    local next_cursor = nil
    if last_index < #items and page[#page] then
        next_cursor = page[#page].id
    end

    return page, next_cursor
end

local function build_content_response(raw_snippets, args, scope_key, user_hash, namespace_state)
    local page, next_cursor = build_virtual_snippet_page(raw_snippets, args, scope_key, user_hash, namespace_state)
    local response = { data = json_array(page) }
    if next_cursor then
        response.cursor = next_cursor
    end
    return response
end

local function build_root_folder_response(root_snippets, namespace_snippets, args, scope_key, user_hash, namespace_state)
    local source_snippets = root_snippets
    if args.name and args.name ~= "" then
        source_snippets = namespace_snippets
    end

    local page, next_cursor = build_virtual_snippet_page(source_snippets, args, scope_key, user_hash, namespace_state)
    local response = {
        data = {
            folders = json_array(build_virtual_folder_array(namespace_state)),
            contents = json_array(page),
        },
    }
    if next_cursor then
        response.cursor = next_cursor
    end
    return response
end

local function build_folder_contents_response(folder_snippets, args, scope_key, user_hash, namespace_state)
    local page, next_cursor = build_virtual_snippet_page(folder_snippets, args, scope_key, user_hash, namespace_state)
    local response = {
        data = {
            folders = json_array({}),
            contents = json_array(page),
        },
    }
    if next_cursor then
        response.cursor = next_cursor
    end
    return response
end

function _M.handle_content()
    local api_project_ref = get_project_ref()
    if not api_project_ref then
        return passthrough_current_request()
    end
    local project_scope = get_project_scope()

    local method = ngx.req.get_method()
    local args = ngx.req.get_uri_args()

    if method == "GET" then
        if args.type ~= "sql" then
            return passthrough_current_request()
        end
        if args.visibility == "project" then
            return respond_json(200, { data = json_array({}) })
        end

        local user_hash, user_hash_err = get_user_hash()
        if not user_hash then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user identity" } })
        end

        local root_folder, namespace_state, folder_err =
            resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, true)
        if not root_folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local snippets, snippets_err
        if args.name and args.name ~= "" then
            snippets, snippets_err = collect_namespace_snippets(api_project_ref, namespace_state, {
                include_root = true,
                include_children = true,
            })
        else
            snippets, snippets_err = collect_namespace_snippets(api_project_ref, namespace_state, {
                actual_folder = root_folder,
            })
        end

        if not snippets then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch user content: ", snippets_err or "unknown error")
            return respond_json(502, { error = { message = "Failed to fetch snippets" } })
        end

        return respond_json(200, build_content_response(snippets, args, project_scope, user_hash, namespace_state))
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

        local root_folder, namespace_state, folder_err =
            resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, true)
        if not root_folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to ensure user folder: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to ensure user folder" } })
        end

        local incoming_id = payload.id
        local requested_virtual_folder_id = payload.folder_id
        local canonical_virtual_id = virtual_snippet_id(payload.name or "", requested_virtual_folder_id)
        local existing = resolve_actual_snippet(
            api_project_ref,
            namespace_state,
            project_scope,
            user_hash,
            incoming_id
        )
        if not existing and canonical_virtual_id ~= incoming_id then
            existing = resolve_actual_snippet(
                api_project_ref,
                namespace_state,
                project_scope,
                user_hash,
                canonical_virtual_id
            )
        end

        local target_folder = resolve_actual_folder(project_scope, user_hash, namespace_state, requested_virtual_folder_id)
        if not target_folder then
            return respond_json(404, { error = { message = "Folder not found" } })
        end

        if existing then
            payload.id = existing.id
        else
            payload.id = incoming_id or canonical_virtual_id
        end

        if type(payload.content) == "table" then
            payload.content.content_id = payload.id
        end

        payload.folder_id = target_folder.id

        local encoded = cjson.encode(payload)
        local res, err = studio_request("PUT", "/api/platform/projects/" .. api_project_ref .. "/content", {
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
            local preferred_virtual_id = incoming_id or canonical_virtual_id
            set_mapped_actual_id(project_scope, user_hash, preferred_virtual_id, saved.id, true)
            if canonical_virtual_id ~= preferred_virtual_id then
                set_mapped_actual_id(project_scope, user_hash, canonical_virtual_id, saved.id, false)
            end
            saved = virtualize_snippet(project_scope, user_hash, namespace_state, saved, preferred_virtual_id)
        end

        return respond_json(res.status, saved)
    end

    if method == "DELETE" then
        local ids = args.ids
        if type(ids) ~= "string" or ids == "" then
            return passthrough_current_request()
        end

        local user_hash, user_hash_err = get_user_hash()
        if not user_hash then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user identity" } })
        end

        local _, namespace_state, folder_err =
            resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, false)
        if not namespace_state then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for delete: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local mapped_ids = {}
        local requested_ids = {}
        for id in string.gmatch(ids, "([^,]+)") do
            local trimmed = (id or ""):gsub("^%s+", ""):gsub("%s+$", "")
            if trimmed ~= "" then
                table.insert(requested_ids, trimmed)
                local actual = resolve_actual_snippet(
                    api_project_ref,
                    namespace_state,
                    project_scope,
                    user_hash,
                    trimmed
                )
                if not actual then
                    return respond_json(404, { error = { message = "Content not found." } })
                end
                table.insert(mapped_ids, actual.id)
            end
        end

        local res, err = studio_request("DELETE", "/api/platform/projects/" .. api_project_ref .. "/content", {
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
    local api_project_ref = get_project_ref()
    if not api_project_ref then
        return passthrough_current_request()
    end
    local project_scope = get_project_scope()

    local method = ngx.req.get_method()
    local args = ngx.req.get_uri_args()

    local user_hash, user_hash_err = get_user_hash()
    if not user_hash then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    if method == "GET" then
        if args.type ~= "sql" then
            return passthrough_current_request()
        end

        local root_folder, namespace_state, folder_err =
            resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, true)
        if not root_folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder for folders route: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local root_snippets, root_err = collect_namespace_snippets(api_project_ref, namespace_state, {
            actual_folder = root_folder,
        })
        if not root_snippets then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch root snippets: ", root_err or "unknown error")
            return respond_json(502, { error = { message = "Failed to fetch folder contents" } })
        end

        local namespace_snippets = root_snippets
        if args.name and args.name ~= "" then
            namespace_snippets, root_err = collect_namespace_snippets(api_project_ref, namespace_state, {
                include_root = true,
                include_children = true,
            })
            if not namespace_snippets then
                ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch namespace snippets: ", root_err or "unknown error")
                return respond_json(502, { error = { message = "Failed to fetch folder contents" } })
            end
        end

        return respond_json(
            200,
            build_root_folder_response(root_snippets, namespace_snippets, args, project_scope, user_hash, namespace_state)
        )
    end

    if method == "POST" then
        local raw_body, body_err = read_body()
        if body_err then
            return respond_json(400, { error = { message = "Failed to read request body" } })
        end

        local payload = cjson_safe.decode(raw_body or "")
        if type(payload) ~= "table" then
            return respond_json(400, { error = { message = "Invalid request body" } })
        end

        if payload.parentId and payload.parentId ~= "" and payload.parentId ~= cjson.null then
            return respond_json(400, { error = { message = "Nested folders are not supported" } })
        end

        local _, _, root_err = resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, true)
        if root_err then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to ensure namespace root before create folder: ", root_err)
            return respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local created, create_err = create_namespaced_folder(api_project_ref, user_hash, project_scope, payload.name)
        if not created then
            return respond_json(500, { error = { message = create_err or "Failed to create folder" } })
        end

        return respond_json(201, created.virtual)
    end

    if method == "DELETE" then
        local raw_ids = args.ids
        local requested_ids = {}

        if type(raw_ids) == "string" then
            for id in string.gmatch(raw_ids, "([^,]+)") do
                local trimmed = (id or ""):gsub("^%s+", ""):gsub("%s+$", "")
                if trimmed ~= "" then
                    table.insert(requested_ids, trimmed)
                end
            end
        elseif type(raw_ids) == "table" then
            for _, id in ipairs(raw_ids) do
                local trimmed = tostring(id or ""):gsub("^%s+", ""):gsub("%s+$", "")
                if trimmed ~= "" then
                    table.insert(requested_ids, trimmed)
                end
            end
        end

        if #requested_ids == 0 then
            return respond_json(400, { error = { message = "Folder IDs are required" } })
        end

        local root_folder, namespace_state, folder_err =
            resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, false)
        if not namespace_state then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for folder delete: ", folder_err or "unknown error")
            return respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local actual_ids = {}
        for _, id in ipairs(requested_ids) do
            local actual_folder = resolve_actual_folder(project_scope, user_hash, namespace_state, id)
            if not actual_folder or (root_folder and actual_folder.id == root_folder.id) then
                return respond_json(404, { error = { message = "Folder not found" } })
            end
            table.insert(actual_ids, actual_folder.id)
        end

        local res, err = studio_request("DELETE", "/api/platform/projects/" .. api_project_ref .. "/content/folders", {
            query = { ids = table.concat(actual_ids, ",") },
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to delete folders: ", err or "unknown error")
            return respond_json(502, { error = { message = "Failed to delete folder" } })
        end

        if res.status < 200 or res.status >= 300 then
            return respond_from_studio(res)
        end

        return respond_json(res.status, {})
    end

    return passthrough_current_request()
end

function _M.handle_folder_item()
    local api_project_ref = get_project_ref()
    local folder_id = ngx.var.uri:match("/content/folders/([^/]+)$")
    if not api_project_ref or not folder_id then
        return passthrough_current_request()
    end

    local project_scope = get_project_scope()
    local method = ngx.req.get_method()

    local user_hash, user_hash_err = get_user_hash()
    if not user_hash then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    local root_folder, namespace_state, folder_err =
        resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, false)
    if not namespace_state then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for folder item: ", folder_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local actual_folder = resolve_actual_folder(project_scope, user_hash, namespace_state, folder_id)
    if not actual_folder or (root_folder and actual_folder.id == root_folder.id) then
        return respond_json(404, { error = { message = "Folder not found" } })
    end

    if method == "GET" then
        local args = ngx.req.get_uri_args()
        local snippets, err = collect_namespace_snippets(api_project_ref, namespace_state, {
            actual_folder = actual_folder,
        })

        if not snippets then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch virtual folder contents: ", err or "unknown error")
            return respond_json(502, { error = { message = "Failed to fetch folder contents" } })
        end

        return respond_json(200, build_folder_contents_response(snippets, args, project_scope, user_hash, namespace_state))
    end

    if method == "PATCH" then
        return respond_json(200, {})
    end

    return passthrough_current_request()
end

function _M.handle_count()
    local api_project_ref = get_project_ref()
    if not api_project_ref then
        return passthrough_current_request()
    end
    local project_scope = get_project_scope()

    local args = ngx.req.get_uri_args()
    if args.type ~= "sql" then
        return passthrough_current_request()
    end

    local user_hash, user_hash_err = get_user_hash()
    if not user_hash then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    local _, namespace_state, folder_err =
        resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, true)
    if not namespace_state then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder for count route: ", folder_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local all_snippets, snippets_err = collect_namespace_snippets(api_project_ref, namespace_state, {
        include_root = true,
        include_children = true,
    })
    if not all_snippets then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch snippets for count: ", snippets_err or "unknown error")
        return respond_json(502, { error = { message = "Failed to fetch snippets for count" } })
    end

    if args.name and args.name ~= "" then
        local search_term = tostring(args.name or ""):lower()
        local count = 0
        for _, snippet in ipairs(all_snippets) do
            if (snippet.name or ""):lower():find(search_term, 1, true) ~= nil then
                count = count + 1
            end
        end
        return respond_json(200, { count = count })
    end

    local favorites = 0
    for _, snippet in ipairs(all_snippets) do
        if snippet.favorite then
            favorites = favorites + 1
        end
    end

    return respond_json(200, {
        shared = 0,
        favorites = favorites,
        private = #all_snippets,
    })
end

function _M.handle_item()
    local api_project_ref = get_project_ref()
    local item_id = ngx.var.uri:match("/content/item/([^/]+)$")
    if not api_project_ref or not item_id then
        return passthrough_current_request()
    end
    local project_scope = get_project_scope()

    local user_hash, user_hash_err = get_user_hash()
    if not user_hash then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user hash: ", user_hash_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    local _, namespace_state, folder_err =
        resolve_namespace_root_folder(api_project_ref, user_hash, project_scope, false)
    if not namespace_state then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for item route: ", folder_err or "unknown error")
        return respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local actual = resolve_actual_snippet(api_project_ref, namespace_state, project_scope, user_hash, item_id)
    if not actual or not actual.id then
        return respond_json(404, { message = "Content not found." })
    end

    local res, err = studio_request("GET", "/api/platform/projects/" .. api_project_ref .. "/content/item/" .. actual.id)
    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch snippet by item id: ", err or "unknown error")
        return respond_json(502, { error = { message = "Failed to fetch snippet" } })
    end

    if res.status ~= 200 then
        return respond_from_studio(res)
    end

    local payload = parse_json_response(res)
    if type(payload) == "table" and payload.name then
        payload = virtualize_snippet(project_scope, user_hash, namespace_state, payload, item_id)
    end

    return respond_json(200, payload)
end

return _M
