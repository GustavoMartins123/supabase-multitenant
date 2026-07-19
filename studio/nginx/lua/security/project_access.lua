local cjson = require("cjson.safe")
local resolver = require("project_context.project_ref_resolver")
local studio_context = require("project_context.studio_context")
local user_context_headers = require("project_context.user_context_headers")

local _M = {}

local function reject(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(cjson.encode({
        error = status == ngx.HTTP_NOT_FOUND and "project_not_found"
            or status == ngx.HTTP_FORBIDDEN and "project_access_denied"
            or "project_context_error",
        message = message or "Project access denied",
    }))
    return ngx.exit(status)
end

function _M.enforce(ref)
    ref = ref or ngx.var.project_ref
    if not resolver.valid_ref(ref) then
        return reject(ngx.HTTP_NOT_FOUND, "Project context is missing from the URL")
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
