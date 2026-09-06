local cjson = require("cjson")
local client = require("studio_compat.content_studio_client")
local namespace = require("studio_compat.content_namespace")

local _M = {}

local json_array = client.json_array
local simple_hash = client.simple_hash
local deterministic_uuid = client.deterministic_uuid

local function virtual_snippet_id(name, virtual_folder_id)
    if virtual_folder_id and virtual_folder_id ~= cjson.null and virtual_folder_id ~= "" then
        return deterministic_uuid({ virtual_folder_id, string.format("%s.sql", name) })
    end

    return deterministic_uuid({ string.format("%s.sql", name) })
end

local function to_virtual_snippet(snippet, virtual_id, virtual_folder_id)
    local cloned = namespace.clone_table(snippet)
    cloned.id = virtual_id or virtual_snippet_id(cloned.name or "")
    cloned.folder_id = virtual_folder_id or cjson.null
    return cloned
end

local function resolve_virtual_snippet_id(project_ref, user_id, snippet, virtual_folder_id, id_namespace)
    if type(snippet) ~= "table" or not snippet.id or snippet.id == "" then
        return nil
    end

    local preferred = namespace.get_preferred_virtual_id(project_ref, user_id, snippet.id)
    if preferred and preferred ~= "" then
        namespace.set_mapped_actual_id(project_ref, user_id, preferred, snippet.id, true)
        return preferred
    end

    local canonical = virtual_snippet_id(snippet.name or "", id_namespace or virtual_folder_id)
    namespace.set_mapped_actual_id(project_ref, user_id, canonical, snippet.id, false)
    return canonical
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

local function virtualize_snippet(scope_key, user_id, namespace_state, snippet, forced_virtual_id)
    local virtual_folder = namespace.resolve_virtual_folder_id_for_snippet(namespace_state, snippet)
    local id_namespace = virtual_folder
    if not id_namespace and namespace_state.root_folder then
        id_namespace = namespace_state.root_folder.id
    end
    local virtual_id = forced_virtual_id
        or resolve_virtual_snippet_id(
            scope_key,
            user_id,
            snippet,
            virtual_folder,
            id_namespace
        )
    return to_virtual_snippet(snippet, virtual_id, virtual_folder)
end

local function resolve_actual_folder(scope_key, user_id, namespace_state, requested_folder_id)
    if requested_folder_id == nil or requested_folder_id == cjson.null or requested_folder_id == "" then
        return namespace_state.root_folder
    end

    local entry = namespace_state.child_by_virtual_id[requested_folder_id]
        or namespace_state.child_by_actual_id[requested_folder_id]
    if entry then
        if user_id and requested_folder_id ~= entry.actual.id then
            namespace.set_mapped_actual_folder_id(scope_key, user_id, requested_folder_id, entry.actual.id, true)
        end
        return entry.actual
    end

    if user_id then
        local mapped_actual_id = namespace.get_mapped_actual_folder_id(scope_key, user_id, requested_folder_id)
        if mapped_actual_id and mapped_actual_id ~= "" then
            entry = namespace_state.child_by_actual_id[mapped_actual_id]
            if entry then
                namespace.set_mapped_actual_folder_id(scope_key, user_id, requested_folder_id, entry.actual.id, true)
                return entry.actual
            end
        end
    end

    for _, folder_entry in ipairs(namespace_state.child_folders) do
        for _, alias in ipairs(folder_entry.aliases or {}) do
            if alias == requested_folder_id then
                if user_id then
                    namespace.set_mapped_actual_folder_id(
                        scope_key,
                        user_id,
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

local function find_actual_snippet_in_collection(scope_key, user_id, request_id, namespace_state, snippets)
    if not request_id or request_id == "" then
        return nil
    end

    local mapped_actual_id = namespace.get_mapped_actual_id(scope_key, user_id, request_id)
    if mapped_actual_id and mapped_actual_id ~= "" then
        for _, snippet in ipairs(snippets or {}) do
            if snippet.id == mapped_actual_id then
                return snippet
            end
        end
    end

    for _, snippet in ipairs(snippets or {}) do
        local virtual_folder = namespace.resolve_virtual_folder_id_for_snippet(namespace_state, snippet)
        local id_namespace = virtual_folder
        if not id_namespace and namespace_state.root_folder then
            id_namespace = namespace_state.root_folder.id
        end

        local canonical_id = virtual_snippet_id(snippet.name, id_namespace)
        local visible_id = resolve_virtual_snippet_id(
            scope_key,
            user_id,
            snippet,
            virtual_folder,
            id_namespace
        )
        local legacy_id = virtual_snippet_id(snippet.name, virtual_folder)
        local matches = snippet.id == request_id
            or canonical_id == request_id
            or visible_id == request_id
            or legacy_id == request_id

        if not matches and snippet.folder_id and snippet.folder_id ~= cjson.null then
            local folder_entry = namespace_state.child_by_actual_id[snippet.folder_id]
            for _, alias in ipairs((folder_entry and folder_entry.aliases) or {}) do
                if virtual_snippet_id(snippet.name, alias) == request_id then
                    matches = true
                    break
                end
            end
        end

        if matches then
            namespace.set_mapped_actual_id(scope_key, user_id, request_id, snippet.id, visible_id == request_id)
            return snippet
        end
    end

    return nil
end

local function resolve_actual_snippet(project_ref, namespace_state, scope_key, user_id, request_id, actual_folder)
    if not request_id or request_id == "" then
        return nil
    end

    local snippets, err = namespace.collect_namespace_snippets(
        project_ref,
        namespace_state,
        actual_folder and { actual_folder = actual_folder } or { include_root = true, include_children = true }
    )
    if not snippets then
        ngx.log(ngx.WARN, "[CONTENT-PROXY] Could not list namespace snippets: ", err or "unknown error")
        return nil
    end

    return find_actual_snippet_in_collection(scope_key, user_id, request_id, namespace_state, snippets)
end

local function build_virtual_folder_array(namespace_state)
    local folders = {}
    for _, entry in ipairs(namespace_state.child_folders) do
        table.insert(folders, namespace.clone_table(entry.virtual))
    end
    return folders
end

local function build_virtual_snippet_page(raw_snippets, args, scope_key, user_id, namespace_state)
    local favorite_filter = parse_boolean(args.favorite)
    local search_term = tostring(args.name or ""):lower()
    local items = {}

    for _, snippet in ipairs(raw_snippets or {}) do
        local virtual = virtualize_snippet(scope_key, user_id, namespace_state, snippet)
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

local function build_content_response(raw_snippets, args, scope_key, user_id, namespace_state)
    local page, next_cursor = build_virtual_snippet_page(raw_snippets, args, scope_key, user_id, namespace_state)
    local response = { data = json_array(page) }
    if next_cursor then
        response.cursor = next_cursor
    end
    return response
end

local function build_root_folder_response(root_snippets, namespace_snippets, args, scope_key, user_id, namespace_state)
    local source_snippets = root_snippets
    if args.name and args.name ~= "" then
        source_snippets = namespace_snippets
    end

    local page, next_cursor = build_virtual_snippet_page(source_snippets, args, scope_key, user_id, namespace_state)
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

local function build_folder_contents_response(folder_snippets, args, scope_key, user_id, namespace_state)
    local page, next_cursor = build_virtual_snippet_page(folder_snippets, args, scope_key, user_id, namespace_state)
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

_M.json_array = json_array
_M.simple_hash = simple_hash
_M.deterministic_uuid = deterministic_uuid
_M.virtual_snippet_id = virtual_snippet_id
_M.to_virtual_snippet = to_virtual_snippet
_M.resolve_virtual_snippet_id = resolve_virtual_snippet_id
_M.normalize_limit = normalize_limit
_M.normalize_sort = normalize_sort
_M.parse_boolean = parse_boolean
_M.virtualize_snippet = virtualize_snippet
_M.resolve_actual_folder = resolve_actual_folder
_M.find_actual_snippet_in_collection = find_actual_snippet_in_collection
_M.resolve_actual_snippet = resolve_actual_snippet
_M.build_virtual_folder_array = build_virtual_folder_array
_M.build_virtual_snippet_page = build_virtual_snippet_page
_M.build_content_response = build_content_response
_M.build_root_folder_response = build_root_folder_response
_M.build_folder_contents_response = build_folder_contents_response

return _M
