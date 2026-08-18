local user_id = ngx.var[1]

local cjson = require("cjson.safe")
local authelia_identifiers = require("admin_api.authelia_identifiers")
local user_store = require("admin_api.authelia_user_store")
local user_sync = require("admin_api.user_sync")
local cache = ngx.shared.users_cache

local user_data = cache:get(user_id)
if not user_data then
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.say('{"error": "User not found"}')
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

local user = cjson.decode(user_data)
if not user then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid user data"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local username = user.username
local caller_id = ngx.var.auth_user_id or ""

local function error_result(status, message)
    return { status = status, payload = { error = message } }
end

local function cache_user()
    local encoded = cjson.encode(user)
    if not encoded then
        return
    end
    cache:set(user_id, encoded)
    if user.user_uuid and user.user_uuid ~= "" then
        cache:set(user.user_uuid, encoded)
    end
end

local result, mutation_err = user_store.with_lock(function()
    local yaml_data, original, load_err = user_store.load()
    if not yaml_data then
        ngx.log(ngx.ERR, "[DEACTIVATE] Failed to read YAML: ", load_err)
        return error_result(
            ngx.HTTP_INTERNAL_SERVER_ERROR,
            "Failed to read user database"
        )
    end

    local user_entry = yaml_data.users[username]
    if not user_entry then
        return error_result(ngx.HTTP_NOT_FOUND, "User not found in database")
    end

    -- Campos projetados para cache/backend precisam vir do snapshot lido sob
    -- lock, nunca do users_cache obtido antes da secao critica.
    user.display_name = user_entry.displayname or username

    local target_is_me = caller_id ~= "" and (
        caller_id == tostring(user.user_uuid or "")
        or caller_id == user_id
    )
    if target_is_me then
        return error_result(
            ngx.HTTP_FORBIDDEN,
            "You cannot deactivate yourself"
        )
    end

    local target_is_admin = false
    local has_inactive = false
    for _, group in ipairs(user_entry.groups or {}) do
        if group == "admin" then
            target_is_admin = true
        elseif group == "inactive" then
            has_inactive = true
        end
    end

    if target_is_admin then
        return error_result(
            ngx.HTTP_FORBIDDEN,
            "Cannot deactivate an admin user"
        )
    end

    if has_inactive then
        user.is_active = false
        cache_user()
        return {
            status = ngx.HTTP_OK,
            payload = { message = "User is already inactive" }
        }
    end

    if not user.user_uuid or user.user_uuid == "" then
        local ensured_user_uuid, _, identifier_err =
            authelia_identifiers.ensure_identifier(username)
        if not ensured_user_uuid then
            local status = tostring(identifier_err or ""):find("busy", 1, true)
                and ngx.HTTP_SERVICE_UNAVAILABLE
                or ngx.HTTP_INTERNAL_SERVER_ERROR
            return error_result(
                status,
                "Failed to generate Authelia opaque identifier"
            )
        end
        user.user_uuid = ensured_user_uuid
    end

    local new_groups = {}
    for _, group in ipairs(user_entry.groups or {}) do
        if group ~= "active" and group ~= "inactive" then
            table.insert(new_groups, group)
        end
    end
    table.insert(new_groups, "inactive")
    user_entry.groups = new_groups

    local written, write_err = user_store.write(yaml_data)
    if not written then
        ngx.log(ngx.ERR, "[DEACTIVATE] Failed to write YAML: ", write_err)
        return error_result(
            ngx.HTTP_INTERNAL_SERVER_ERROR,
            "Failed to update user database"
        )
    end

    local sync_result, sync_err = user_sync.sync_user({
        id = user.user_uuid,
        username = username,
        display_name = user.display_name,
        groups = user_entry.groups,
        is_active = false
    })

    if sync_err then
        ngx.log(ngx.ERR, "[DEACTIVATE] Failed to sync user with backend: ", sync_err)
        local restored, restore_err = user_store.restore(original)
        if not restored then
            ngx.log(
                ngx.CRIT,
                "[DEACTIVATE] Failed to rollback users database: ",
                restore_err
            )
            return error_result(
                ngx.HTTP_INTERNAL_SERVER_ERROR,
                "User synchronization failed and Authelia rollback also failed"
            )
        end
        return error_result(
            ngx.HTTP_BAD_GATEWAY,
            "User deactivated in Authelia but failed to sync with backend"
        )
    end

    if type(sync_result) == "table" and sync_result.id then
        user.user_uuid = sync_result.id
    end
    user.is_active = false
    cache_user()

    return {
        status = ngx.HTTP_OK,
        payload = {
            message = "User deactivated successfully",
            user = {
                id = user.user_uuid or user_id,
                username = username,
                display_name = user.display_name,
                status = "deactivated"
            },
            timestamp = os.time()
        }
    }
end)

if not result then
    local status = tostring(mutation_err or ""):find("busy", 1, true)
        and ngx.HTTP_SERVICE_UNAVAILABLE
        or ngx.HTTP_INTERNAL_SERVER_ERROR
    result = error_result(status, mutation_err or "Failed to update user database")
end

ngx.status = result.status
ngx.header.content_type = "application/json"
if result.status == ngx.HTTP_SERVICE_UNAVAILABLE then
    ngx.header["Retry-After"] = "1"
end
ngx.say(cjson.encode(result.payload))
return ngx.exit(result.status)
