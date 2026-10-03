local cjson = require("cjson")
local client = require("studio_compat.content_studio_client")
local content_project_identity = require("studio_compat.content_project_identity")

local _M = {}

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

                local canonical_virtual_id = virtual_folder_id(user_id, project_scope, visible_name)

                local virtual = {
                    id = canonical_virtual_id,
                    name = visible_name,
                    owner_id = folder.owner_id or 1,
                    parent_id = cjson.null,
                    project_id = folder.project_id or 1,
                }
                local entry = {
                    actual = folder,
                    virtual = virtual,
                    canonical_virtual_id = canonical_virtual_id,
                }
                table.insert(state.child_folders, entry)
                state.child_by_actual_id[folder.id] = entry
                state.child_by_virtual_id[virtual.id] = entry
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
_M.clone_table = clone_table
_M.list_all_folders = list_all_folders
_M.load_namespace_state = load_namespace_state
_M.resolve_namespace_root_folder = resolve_namespace_root_folder
_M.create_namespaced_folder = create_namespaced_folder
_M.list_user_snippets = list_user_snippets
_M.collect_namespace_snippets = collect_namespace_snippets
_M.resolve_virtual_folder_id_for_snippet = resolve_virtual_folder_id_for_snippet

return _M
