local module_arg = ...
local cjson = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")
local user_store = require("admin_api.authelia_user_store")

local M = {}

local function respond_error(status, code, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    if status == ngx.HTTP_SERVICE_UNAVAILABLE then
        ngx.header["Retry-After"] = "1"
    end
    ngx.say(cjson.encode({ error = code, message = message }))
    return ngx.exit(status)
end

local function is_valid_argon2_hash(value)
    return type(value) == "string"
        and #value > 0
        and #value <= 4096
        and value:match("^%$argon2") ~= nil
end

function M.reconcile_password_change(before_data, after_data)
    if type(before_data) ~= "table" or type(before_data.users) ~= "table" then
        return nil, "invalid baseline user database"
    end
    if type(after_data) ~= "table" or type(after_data.users) ~= "table" then
        return nil, "invalid updated user database"
    end
    for username in pairs(after_data.users) do
        if before_data.users[username] == nil then
            return nil, "unexpected user added during password mutation"
        end
    end

    local changed = {}
    for username, before_user in pairs(before_data.users) do
        local after_user = after_data.users[username]
        if type(after_user) == "table" and after_user.password ~= before_user.password then
            if not is_valid_argon2_hash(after_user.password) then
                return nil, "invalid password hash written by provider"
            end
            changed[#changed + 1] = { username = username, password = after_user.password }
        end
    end

    if #changed > 1 then
        return nil, "multiple user passwords changed during single request"
    end

    if #changed == 1 then
        local item = changed[1]
        before_data.users[item.username].password = item.password
    end

    return before_data, nil, #changed
end

local function forward_response(res)
    ngx.status = res.status
    if type(res.header) == "table" then
        for _, name in ipairs({
            "Content-Type",
            "Set-Cookie",
            "Cache-Control",
            "Pragma",
            "WWW-Authenticate",
            "Retry-After",
        }) do
            if res.header[name] ~= nil then
                ngx.header[name] = res.header[name]
            end
        end
    end
    ngx.print(res.body or "")
    return ngx.exit(res.status)
end

function M.handle()
    if ngx.req.get_method() ~= "POST" then
        ngx.header["Allow"] = "POST"
        return respond_error(ngx.HTTP_METHOD_NOT_ALLOWED, "method_not_allowed", "Method not allowed")
    end

    local body, read_err = internal_hmac.read_current_body()
    if body == nil then
        return respond_error(ngx.HTTP_BAD_REQUEST, "invalid_request_body", read_err or "Failed to read body")
    end

    local result, lock_err = user_store.with_lock(function()
        local before_data, before_raw, load_err = user_store.load()
        if not before_data then
            return { error_status = ngx.HTTP_SERVICE_UNAVAILABLE, code = "directory_unavailable", message = load_err or "User database unavailable" }
        end

        local capture_uri = "/internal/authelia-password-mutation"
        local args = ngx.var.args
        if args and args ~= "" then
            capture_uri = capture_uri .. "?" .. args
        end

        local res = ngx.location.capture(capture_uri, {
            method = ngx.HTTP_POST,
            body = body,
            always_forward_body = true,
            vars = { authelia_mutation_uri = ngx.var.uri },
        })
        if not res or not res.status then
            return { error_status = ngx.HTTP_BAD_GATEWAY, code = "authelia_unavailable", message = "Identity provider request failed" }
        end

        if res.status >= 200 and res.status < 300 then
            local after_data, _, after_err = user_store.load()
            if not after_data then
                user_store.restore(before_raw)
                return { error_status = ngx.HTTP_SERVICE_UNAVAILABLE, code = "directory_reconcile_failed", message = after_err or "Failed to read updated user database" }
            end
            local merged, reconcile_err = M.reconcile_password_change(before_data, after_data)
            if not merged then
                user_store.restore(before_raw)
                return { error_status = ngx.HTTP_SERVICE_UNAVAILABLE, code = "directory_reconcile_failed", message = reconcile_err }
            end
            local written, write_err = user_store.write(merged)
            if not written then
                user_store.restore(before_raw)
                return { error_status = ngx.HTTP_SERVICE_UNAVAILABLE, code = "directory_write_failed", message = write_err or "Failed to persist password update" }
            end
        elseif res.status >= 400 then
            local after_raw = user_store.read_raw()
            if after_raw and after_raw ~= before_raw then
                user_store.restore(before_raw)
            end
        end

        return { response = res }
    end)

    if not result then
        local status = tostring(lock_err or ""):find("busy", 1, true)
            and ngx.HTTP_SERVICE_UNAVAILABLE
            or ngx.HTTP_INTERNAL_SERVER_ERROR
        return respond_error(status, "directory_busy", lock_err or "Failed to serialize password update")
    end

    if result.error_status then
        return respond_error(result.error_status, result.code, result.message)
    end

    return forward_response(result.response)
end

if type(module_arg) ~= "string" and ngx and ngx.req then
    return M.handle()
end

return M
