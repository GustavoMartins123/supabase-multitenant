local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local client = require("studio_compat.content_studio_client")
local namespace = require("studio_compat.content_namespace")
local virt = require("studio_compat.content_virtualization")

local _M = {}

local json_array = client.json_array

function _M.handle_content()
    local api_project_ref = client.get_project_ref()
    if not api_project_ref then
        return client.passthrough_current_request()
    end
    local project_scope = client.require_project_scope()

    local method = ngx.req.get_method()
    local args = ngx.req.get_uri_args()

    if method == "GET" then
        if args.type ~= "sql" then
            return client.passthrough_current_request()
        end
        if args.visibility == "project" then
            return client.respond_json(200, { data = json_array({}) })
        end

        local user_id, user_id_err = client.get_user_id()
        if not user_id then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
        end

        local root_folder, namespace_state, folder_err =
            namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
        if not root_folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder: ", folder_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local snippets, snippets_err
        if args.name and args.name ~= "" then
            snippets, snippets_err = namespace.collect_namespace_snippets(api_project_ref, namespace_state, {
                include_root = true,
                include_children = true,
            })
        else
            snippets, snippets_err = namespace.collect_namespace_snippets(api_project_ref, namespace_state, {
                actual_folder = root_folder,
            })
        end

        if not snippets then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch user content: ", snippets_err or "unknown error")
            return client.respond_json(502, { error = { message = "Failed to fetch snippets" } })
        end

        return client.respond_json(200, virt.build_content_response(snippets, args, project_scope, user_id, namespace_state))
    end

    if method == "PUT" then
        local raw_body, body_err = client.read_body()
        if body_err then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to read request body: ", body_err)
            return client.respond_json(400, { error = { message = "Failed to read request body" } })
        end

        local payload = cjson_safe.decode(raw_body or "")
        if type(payload) ~= "table" or payload.type ~= "sql" then
            return client.passthrough_current_request(nil, nil, raw_body)
        end

        if payload.visibility == "project" then
            return client.passthrough_current_request(nil, nil, raw_body)
        end

        local user_id, user_id_err = client.get_user_id()
        if not user_id then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
        end

        local root_folder, namespace_state, folder_err =
            namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, true)
        if not root_folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to ensure user folder: ", folder_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to ensure user folder" } })
        end

        local incoming_id = payload.id
        local requested_virtual_folder_id = payload.folder_id
        local target_folder = virt.resolve_actual_folder(
            project_scope,
            user_id,
            namespace_state,
            requested_virtual_folder_id
        )
        if not target_folder then
            return client.respond_json(404, { error = { message = "Folder not found" } })
        end

        local id_namespace = requested_virtual_folder_id
        if id_namespace == nil or id_namespace == cjson.null or id_namespace == "" then
            id_namespace = target_folder.id
        end
        local canonical_virtual_id = virt.virtual_snippet_id(payload.name or "", id_namespace)
        local existing = virt.resolve_actual_snippet(
            api_project_ref,
            namespace_state,
            project_scope,
            user_id,
            incoming_id
        )
        if not existing and canonical_virtual_id ~= incoming_id then
            existing = virt.resolve_actual_snippet(
                api_project_ref,
                namespace_state,
                project_scope,
                user_id,
                canonical_virtual_id
            )
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
        local res, err = client.studio_request("PUT", "/api/platform/projects/" .. api_project_ref .. "/content", {
            body = encoded,
            headers = { ["Content-Type"] = "application/json" },
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to upsert snippet: ", err or "unknown error")
            return client.respond_json(502, { error = { message = "Failed to save snippet" } })
        end

        if res.status < 200 or res.status >= 300 then
            return client.respond_from_studio(res)
        end

        local saved = client.parse_json_response(res)
        if type(saved) == "table" and saved.name then
            local preferred_virtual_id = incoming_id or canonical_virtual_id
            namespace.set_mapped_actual_id(project_scope, user_id, preferred_virtual_id, saved.id, true)
            if canonical_virtual_id ~= preferred_virtual_id then
                namespace.set_mapped_actual_id(project_scope, user_id, canonical_virtual_id, saved.id, false)
            end
            saved = virt.virtualize_snippet(project_scope, user_id, namespace_state, saved, preferred_virtual_id)
        end

        return client.respond_json(res.status, saved)
    end

    if method == "DELETE" then
        local ids = args.ids
        if type(ids) ~= "string" or ids == "" then
            return client.passthrough_current_request()
        end

        local user_id, user_id_err = client.get_user_id()
        if not user_id then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
        end

        local _, namespace_state, folder_err =
            namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
        if not namespace_state then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for delete: ", folder_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local mapped_ids = {}
        local requested_ids = {}
        for id in string.gmatch(ids, "([^,]+)") do
            local trimmed = (id or ""):gsub("^%s+", ""):gsub("%s+$", "")
            if trimmed ~= "" then
                table.insert(requested_ids, trimmed)
                local actual = virt.resolve_actual_snippet(
                    api_project_ref,
                    namespace_state,
                    project_scope,
                    user_id,
                    trimmed
                )
                if not actual then
                    return client.respond_json(404, { error = { message = "Content not found." } })
                end
                table.insert(mapped_ids, actual.id)
            end
        end

        local res, err = client.studio_request("DELETE", "/api/platform/projects/" .. api_project_ref .. "/content", {
            query = { ids = table.concat(mapped_ids, ",") },
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to delete snippets: ", err or "unknown error")
            return client.respond_json(502, { error = { message = "Failed to delete snippets" } })
        end

        if res.status < 200 or res.status >= 300 then
            return client.respond_from_studio(res)
        end

        local response = {}
        for _, id in ipairs(requested_ids) do
            table.insert(response, { id = id })
        end

        return client.respond_json(res.status, json_array(response))
    end

    return client.passthrough_current_request()
end

function _M.handle_folders()
    local api_project_ref = client.get_project_ref()
    if not api_project_ref then
        return client.passthrough_current_request()
    end
    local project_scope = client.require_project_scope()

    local method = ngx.req.get_method()
    local args = ngx.req.get_uri_args()

    local user_id, user_id_err = client.get_user_id()
    if not user_id then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    if method == "GET" then
        if args.type ~= "sql" then
            return client.passthrough_current_request()
        end

        local root_folder, namespace_state, folder_err =
            namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
        if not root_folder then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder for folders route: ", folder_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local root_snippets, root_err = namespace.collect_namespace_snippets(api_project_ref, namespace_state, {
            actual_folder = root_folder,
        })
        if not root_snippets then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch root snippets: ", root_err or "unknown error")
            return client.respond_json(502, { error = { message = "Failed to fetch folder contents" } })
        end

        local namespace_snippets = root_snippets
        if args.name and args.name ~= "" then
            namespace_snippets, root_err = namespace.collect_namespace_snippets(api_project_ref, namespace_state, {
                include_root = true,
                include_children = true,
            })
            if not namespace_snippets then
                ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch namespace snippets: ", root_err or "unknown error")
                return client.respond_json(502, { error = { message = "Failed to fetch folder contents" } })
            end
        end

        return client.respond_json(
            200,
            virt.build_root_folder_response(root_snippets, namespace_snippets, args, project_scope, user_id, namespace_state)
        )
    end

    if method == "POST" then
        local raw_body, body_err = client.read_body()
        if body_err then
            return client.respond_json(400, { error = { message = "Failed to read request body" } })
        end

        local payload = cjson_safe.decode(raw_body or "")
        if type(payload) ~= "table" then
            return client.respond_json(400, { error = { message = "Invalid request body" } })
        end

        if payload.parentId and payload.parentId ~= "" and payload.parentId ~= cjson.null then
            return client.respond_json(400, { error = { message = "Nested folders are not supported" } })
        end

        local _, _, root_err = namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, true)
        if root_err then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to ensure namespace root before create folder: ", root_err)
            return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local created, create_err = namespace.create_namespaced_folder(api_project_ref, user_id, project_scope, payload.name)
        if not created then
            return client.respond_json(500, { error = { message = create_err or "Failed to create folder" } })
        end

        return client.respond_json(201, created.virtual)
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
            return client.respond_json(400, { error = { message = "Folder IDs are required" } })
        end

        local root_folder, namespace_state, folder_err =
            namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
        if not namespace_state then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for folder delete: ", folder_err or "unknown error")
            return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
        end

        local actual_ids = {}
        for _, id in ipairs(requested_ids) do
            local actual_folder = virt.resolve_actual_folder(project_scope, user_id, namespace_state, id)
            if not actual_folder or (root_folder and actual_folder.id == root_folder.id) then
                return client.respond_json(404, { error = { message = "Folder not found" } })
            end
            table.insert(actual_ids, actual_folder.id)
        end

        local res, err = client.studio_request("DELETE", "/api/platform/projects/" .. api_project_ref .. "/content/folders", {
            query = { ids = table.concat(actual_ids, ",") },
        })

        if not res then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to delete folders: ", err or "unknown error")
            return client.respond_json(502, { error = { message = "Failed to delete folder" } })
        end

        if res.status < 200 or res.status >= 300 then
            return client.respond_from_studio(res)
        end

        return client.respond_json(res.status, {})
    end

    return client.passthrough_current_request()
end

function _M.handle_folder_item()
    local api_project_ref = client.get_project_ref()
    local folder_id = ngx.var.uri:match("/content/folders/([^/]+)$")
    if not api_project_ref or not folder_id then
        return client.passthrough_current_request()
    end

    local project_scope = client.require_project_scope()
    local method = ngx.req.get_method()

    local user_id, user_id_err = client.get_user_id()
    if not user_id then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    local root_folder, namespace_state, folder_err =
        namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
    if not namespace_state then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for folder item: ", folder_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local actual_folder = virt.resolve_actual_folder(project_scope, user_id, namespace_state, folder_id)
    if not actual_folder or (root_folder and actual_folder.id == root_folder.id) then
        return client.respond_json(404, { error = { message = "Folder not found" } })
    end

    if method == "GET" then
        local args = ngx.req.get_uri_args()
        local snippets, err = namespace.collect_namespace_snippets(api_project_ref, namespace_state, {
            actual_folder = actual_folder,
        })

        if not snippets then
            ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch virtual folder contents: ", err or "unknown error")
            return client.respond_json(502, { error = { message = "Failed to fetch folder contents" } })
        end

        return client.respond_json(200, virt.build_folder_contents_response(snippets, args, project_scope, user_id, namespace_state))
    end

    if method == "PATCH" then
        return client.respond_json(200, {})
    end

    return client.passthrough_current_request()
end

function _M.handle_count()
    local api_project_ref = client.get_project_ref()
    if not api_project_ref then
        return client.passthrough_current_request()
    end
    local project_scope = client.require_project_scope()

    local args = ngx.req.get_uri_args()
    if args.type ~= "sql" then
        return client.passthrough_current_request()
    end

    local user_id, user_id_err = client.get_user_id()
    if not user_id then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    local _, namespace_state, folder_err =
        namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
    if not namespace_state then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve user folder for count route: ", folder_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local all_snippets, snippets_err = namespace.collect_namespace_snippets(api_project_ref, namespace_state, {
        include_root = true,
        include_children = true,
    })
    if not all_snippets then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch snippets for count: ", snippets_err or "unknown error")
        return client.respond_json(502, { error = { message = "Failed to fetch snippets for count" } })
    end

    if args.name and args.name ~= "" then
        local search_term = tostring(args.name or ""):lower()
        local count = 0
        for _, snippet in ipairs(all_snippets) do
            if (snippet.name or ""):lower():find(search_term, 1, true) ~= nil then
                count = count + 1
            end
        end
        return client.respond_json(200, { count = count })
    end

    local favorites = 0
    for _, snippet in ipairs(all_snippets) do
        if snippet.favorite then
            favorites = favorites + 1
        end
    end

    return client.respond_json(200, {
        shared = 0,
        favorites = favorites,
        private = #all_snippets,
    })
end

function _M.handle_item()
    local api_project_ref = client.get_project_ref()
    local item_id = ngx.var.uri:match("/content/item/([^/]+)$")
    if not api_project_ref or not item_id then
        return client.passthrough_current_request()
    end
    local project_scope = client.require_project_scope()

    local user_id, user_id_err = client.get_user_id()
    if not user_id then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to get user id: ", user_id_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user identity" } })
    end

    local _, namespace_state, folder_err =
        namespace.resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)
    if not namespace_state then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to resolve namespace for item route: ", folder_err or "unknown error")
        return client.respond_json(500, { error = { message = "Failed to resolve user folder" } })
    end

    local actual = virt.resolve_actual_snippet(api_project_ref, namespace_state, project_scope, user_id, item_id)
    if not actual or not actual.id then
        return client.respond_json(404, { message = "Content not found." })
    end

    local res, err = client.studio_request("GET", "/api/platform/projects/" .. api_project_ref .. "/content/item/" .. actual.id)
    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Failed to fetch snippet by item id: ", err or "unknown error")
        return client.respond_json(502, { error = { message = "Failed to fetch snippet" } })
    end

    if res.status ~= 200 then
        return client.respond_from_studio(res)
    end

    local payload = client.parse_json_response(res)
    if type(payload) == "table" and payload.name then
        payload = virt.virtualize_snippet(project_scope, user_id, namespace_state, payload, item_id)
    end

    return client.respond_json(200, payload)
end

return _M
