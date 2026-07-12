local cjson = require("cjson.safe")
local store = require("admin_api.user_profile_store")
local user_sync = require("admin_api.user_sync")

local M = {}

local function respond(status, payload)
    ngx.status = status
    ngx.header.content_type = "application/json; charset=utf-8"
    ngx.say(cjson.encode(payload))
    return ngx.exit(status)
end

local function sync_profile(profile)
    return user_sync.sync_user({
        id = profile.user_id,
        username = profile.username,
        display_name = profile.display_name,
        groups = profile.groups,
        is_active = profile.is_active,
        source = {
            name = "studio_profile",
            email = profile.email,
            profile = profile,
        },
    })
end

local function read_json_body()
    ngx.req.read_body()
    local body = ngx.req.get_body_data()
    if not body then
        local path = ngx.req.get_body_file()
        if path then
            local file, err = io.open(path, "rb")
            if not file then
                return nil, err
            end
            body = file:read("*a")
            file:close()
        end
    end
    if not body or body == "" then
        return nil, "request body is required"
    end
    local payload = cjson.decode(body)
    if type(payload) ~= "table" then
        return nil, "invalid JSON payload"
    end
    return payload
end

function M.handle()
    local email = ngx.var.authelia_email or ""
    if email == "" then
        return respond(401, { error = "authenticated email is missing" })
    end

    local method = ngx.req.get_method()
    if method == "GET" then
        local profile, err = store.get(email)
        if not profile then
            return respond(500, { error = err or "failed to load profile" })
        end
        local _, sync_err = sync_profile(profile)
        if sync_err then
            ngx.log(ngx.WARN, "[USER_PROFILE] profile projection sync failed: ", sync_err)
        end
        return respond(200, profile)
    end

    if method == "PATCH" then
        local payload, body_err = read_json_body()
        if not payload then
            return respond(400, { error = body_err })
        end
        local profile, update_err = store.update(email, payload, sync_profile)
        if not profile then
            local status = update_err and update_err:find("immutable", 1, true) and 409 or 400
            if update_err and update_err:find("synchron", 1, true) then
                status = 502
            end
            return respond(status, { error = update_err or "failed to update profile" })
        end
        return respond(200, profile)
    end

    return respond(405, { error = "method not allowed" })
end

return M
