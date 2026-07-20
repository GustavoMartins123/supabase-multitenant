local cjson = require("cjson.safe")
local request_context = require("project_context.request_context")
local studio_context = require("project_context.studio_context")
local user_context_headers = require("project_context.user_context_headers")

local _M = {}

local function reject(status, message, error_code)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(cjson.encode({
        error = error_code
            or status == ngx.HTTP_NOT_FOUND and "project_not_found"
            or status == ngx.HTTP_FORBIDDEN and "project_access_denied"
            or "project_context_error",
        message = message or "Project access denied",
    }))
    return ngx.exit(status)
end

local function reject_resolution(err)
    if err == "project_ref_mismatch" then
        return reject(
            ngx.HTTP_CONFLICT,
            "Project reference does not match the current tab",
            err
        )
    end
    if err == "invalid_path_ref"
        or err == "invalid_header_ref"
        or err == "invalid_expected_ref"
    then
        return reject(ngx.HTTP_BAD_REQUEST, "Invalid project reference", err)
    end
    if err == "project_ref_missing" then
        return reject(
            ngx.HTTP_NOT_FOUND,
            "Project context is missing from the request",
            err
        )
    end

    ngx.log(ngx.ERR, "Project context initialization failed: ", err or "unknown")
    return reject(
        ngx.HTTP_INTERNAL_SERVER_ERROR,
        "Project context could not be initialized",
        err
    )
end

function _M.enforce(expected_ref)
    local ref, resolution_err = request_context.capture(expected_ref)
    if not ref then
        return reject_resolution(resolution_err)
    end

    local existing = ngx.ctx.studio_project_context
    if existing and existing.ref == ref then
        return existing
    end

    local email = ngx.var.authelia_email or ""
    if email == "" then
        return reject(ngx.HTTP_UNAUTHORIZED, "Authentication required")
    end
    user_context_headers.apply(email, ngx.var.authelia_groups or "")

    local context, err, status = studio_context.load(ref)
    if not context then
        return reject(status or ngx.HTTP_BAD_GATEWAY, err)
    end

    ngx.ctx.studio_project_context = context
    return context
end

return _M
