local cjson = require("cjson")
local client = require("studio_compat.content_studio_client")
local content_project_identity = require("studio_compat.content_project_identity")
local content_namespace_migration = require("studio_compat.content_namespace_migration")

local _M = {}

local id_map_cache = ngx.shared.service_keys

local simple_hash = client.simple_hash
local deterministic_uuid = client.deterministic_uuid

local function build_folder_name(user_id, project_scope)
    local normalized_scope = tostring(project_scope or ""):gsub("[^%w._-]", "_")
    if normalized_scope == "" or normalized_scope == "default" then
        return user_id
    end

    return string.format("%s__%s", user_id, normalized_scope)
end

local function build_folder_prefix(user_id, project_scope)
    return build_folder_name(user_id, project_scope) .. "__"
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

local function actual_child_folder_name(user_id, project_scope, visible_name)
    return build_folder_prefix(user_id, project_scope) .. visible_name
end

local function actual_folder_id(folder_name)
    return deterministic_uuid({ folder_name })
end

local function actual_snippet_id(folder_id, name)
    return deterministic_uuid({ folder_id, string.format("%s.sql", name) })
end

local function virtual_folder_id(user_id, project_scope, visible_name)
    return deterministic_uuid({ build_folder_name(user_id, project_scope), visible_name })
end

local function snippet_map_key(project_ref, user_id, request_id)
    return table.concat({
        "snippet-id-map",
        project_ref or "",
        user_id or "",
        request_id or "",
    }, ":")
end

local function actual_map_key(project_ref, user_id, actual_id)
    return table.concat({
        "snippet-actual-map",
        project_ref or "",
        user_id or "",
        actual_id or "",
    }, ":")
end

local function folder_map_key(project_ref, user_id, request_id)
    return table.concat({
        "folder-id-map",
        project_ref or "",
        user_id or "",
        request_id or "",
    }, ":")
end

local function folder_actual_map_key(project_ref, user_id, actual_id)
    return table.concat({
        "folder-actual-map",
        project_ref or "",
        user_id or "",
        actual_id or "",
    }, ":")
end

local function get_mapped_actual_id(project_ref, user_id, request_id)
    if not id_map_cache or not project_ref or not user_id or not request_id or request_id == "" then
        return nil
    end

    return id_map_cache:get(snippet_map_key(project_ref, user_id, request_id))
end

local function get_preferred_virtual_id(project_ref, user_id, actual_id)
    if not id_map_cache or not project_ref or not user_id or not actual_id or actual_id == "" then
        return nil
    end

    return id_map_cache:get(actual_map_key(project_ref, user_id, actual_id))
end

local function get_mapped_actual_folder_id(project_ref, user_id, request_id)
    if not id_map_cache or not project_ref or not user_id or not request_id or request_id == "" then
        return nil
    end

    return id_map_cache:get(folder_map_key(project_ref, user_id, request_id))
end

local function get_preferred_virtual_folder_id(project_ref, user_id, actual_id)
    if not id_map_cache or not project_ref or not user_id or not actual_id or actual_id == "" then
        return nil
    end

    return id_map_cache:get(folder_actual_map_key(project_ref, user_id, actual_id))
end

local function set_mapped_actual_id(project_ref, user_id, request_id, actual_id, remember_as_preferred)
    if not id_map_cache or not project_ref or not user_id or not request_id or request_id == "" then
        return
    end
    if not actual_id or actual_id == "" then
        return
    end

    id_map_cache:set(snippet_map_key(project_ref, user_id, request_id), actual_id, 86400)

    if remember_as_preferred then
        id_map_cache:set(actual_map_key(project_ref, user_id, actual_id), request_id, 86400)
    end
end

local function set_mapped_actual_folder_id(project_ref, user_id, request_id, actual_id, remember_as_preferred)
    if not id_map_cache or not project_ref or not user_id or not request_id or request_id == "" then
        return
    end
    if not actual_id or actual_id == "" then
        return
    end

    id_map_cache:set(folder_map_key(project_ref, user_id, request_id), actual_id, 86400)

    if remember_as_preferred then
        id_map_cache:set(folder_actual_map_key(project_ref, user_id, actual_id), request_id, 86400)
    end
end

local function append_unique(items, seen, value)
    if not value or value == "" or seen[value] then
        return
    end

    seen[value] = true
    table.insert(items, value)
end

local function build_folder_aliases(user_id, project_scope, folder, visible_name)
    local aliases = {}
    local seen = {}

    append_unique(aliases, seen, virtual_folder_id(user_id, project_scope, visible_name))

    local selected_ref = client.get_selected_project_ref()
    local identity = selected_ref and content_project_identity.resolve(selected_ref) or nil
    for _, legacy_scope in ipairs((identity and identity.aliases) or {}) do
        if legacy_scope ~= project_scope then
            append_unique(aliases, seen, virtual_folder_id(user_id, legacy_scope, visible_name))
        end
    end

    append_unique(aliases, seen, virtual_folder_id(user_id, "default", visible_name))
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

local function list_all_folders(project_ref)
    local res, err = client.studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders", {
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

    local payload = client.parse_json_response(res)
    return (((payload or {}).data or {}).folders) or {}
end

local function load_namespace_state(project_ref, user_id, project_scope)
    local folders, err = list_all_folders(project_ref)
    if not folders then
        return nil, err
    end

    local root_name = build_folder_name(user_id, project_scope)
    local prefix = build_folder_prefix(user_id, project_scope)
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

                local preferred_virtual_id = get_preferred_virtual_folder_id(project_scope, user_id, folder.id)
                local aliases = build_folder_aliases(user_id, project_scope, folder, visible_name)
                local canonical_virtual_id = aliases[1]
                local resolved_virtual_id = preferred_virtual_id
                if not resolved_virtual_id or resolved_virtual_id == "" then
                    resolved_virtual_id = canonical_virtual_id
                end

                set_mapped_actual_folder_id(project_scope, user_id, canonical_virtual_id, folder.id, false)
                if resolved_virtual_id ~= canonical_virtual_id then
                    set_mapped_actual_folder_id(project_scope, user_id, resolved_virtual_id, folder.id, true)
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

local function resolve_namespace_root_folder(project_ref, user_id, project_scope, create_if_missing)
    local selected_ref = client.get_selected_project_ref()
    local identity, identity_err = content_project_identity.resolve(selected_ref)
    if not identity or identity.project_id ~= project_scope then
        return nil, nil, identity_err or "stable project identity mismatch"
    end

    local migrated, migration_err = content_namespace_migration.ensure(user_id, identity)
    if not migrated then
        return nil, nil, "legacy namespace migration failed: " .. (migration_err or "unknown error")
    end

    local state, state_err = load_namespace_state(project_ref, user_id, project_scope)
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

    local create_res, create_err = client.studio_request("POST", "/api/platform/projects/" .. project_ref .. "/content/folders", {
        body = cjson.encode({ name = state.root_name }),
        headers = { ["Content-Type"] = "application/json" },
    })

    if not create_res then
        return nil, nil, "failed to create folder: " .. (create_err or "unknown error")
    end

    local refreshed, refreshed_err = load_namespace_state(project_ref, user_id, project_scope)
    if refreshed and refreshed.root_folder then
        return refreshed.root_folder, refreshed
    end

    return nil, nil, refreshed_err or "failed to resolve user folder"
end

local function create_namespaced_folder(project_ref, user_id, project_scope, visible_name)
    local safe_name, safe_err = sanitize_folder_segment(visible_name)
    if not safe_name then
        return nil, safe_err
    end

    local state, state_err = load_namespace_state(project_ref, user_id, project_scope)
    if not state then
        return nil, state_err
    end

    if state.child_by_visible_name[safe_name] then
        return nil, "Folder already exists"
    end

    local actual_name = actual_child_folder_name(user_id, project_scope, safe_name)
    local create_res, create_err = client.studio_request("POST", "/api/platform/projects/" .. project_ref .. "/content/folders", {
        body = cjson.encode({ name = actual_name }),
        headers = { ["Content-Type"] = "application/json" },
    })

    if not create_res then
        return nil, "failed to create folder: " .. (create_err or "unknown error")
    end

    local refreshed, refreshed_err = load_namespace_state(project_ref, user_id, project_scope)
    if refreshed and refreshed.child_by_visible_name[safe_name] then
        return refreshed.child_by_visible_name[safe_name], refreshed
    end

    return nil, refreshed_err or "failed to resolve created folder"
end

local function list_user_snippets(project_ref, folder_id)
    local res, err = client.studio_request("GET", "/api/platform/projects/" .. project_ref .. "/content/folders/" .. folder_id, {
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

    local payload = client.parse_json_response(res)
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

_M.build_folder_name = build_folder_name
_M.build_folder_prefix = build_folder_prefix
_M.sanitize_folder_segment = sanitize_folder_segment
_M.actual_child_folder_name = actual_child_folder_name
_M.actual_folder_id = actual_folder_id
_M.actual_snippet_id = actual_snippet_id
_M.virtual_folder_id = virtual_folder_id
_M.snippet_map_key = snippet_map_key
_M.actual_map_key = actual_map_key
_M.folder_map_key = folder_map_key
_M.folder_actual_map_key = folder_actual_map_key
_M.get_mapped_actual_id = get_mapped_actual_id
_M.get_preferred_virtual_id = get_preferred_virtual_id
_M.get_mapped_actual_folder_id = get_mapped_actual_folder_id
_M.get_preferred_virtual_folder_id = get_preferred_virtual_folder_id
_M.set_mapped_actual_id = set_mapped_actual_id
_M.set_mapped_actual_folder_id = set_mapped_actual_folder_id
_M.append_unique = append_unique
_M.build_folder_aliases = build_folder_aliases
_M.clone_table = clone_table
_M.list_all_folders = list_all_folders
_M.load_namespace_state = load_namespace_state
_M.resolve_namespace_root_folder = resolve_namespace_root_folder
_M.create_namespaced_folder = create_namespaced_folder
_M.list_user_snippets = list_user_snippets
_M.collect_namespace_snippets = collect_namespace_snippets
_M.resolve_virtual_folder_id_for_snippet = resolve_virtual_folder_id_for_snippet

return _M
