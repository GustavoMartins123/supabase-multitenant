local internal_hmac = require("security.internal_hmac")
local ref_resolver = require("project_context.project_ref_resolver")

local SECRET = os.getenv("STUDIO_GATEWAY_HMAC_SECRET") or ""
local SERVICE = "studio-nginx"

local M = {}

local function append_query(target)
    local args = ngx.var.args
    if args and args ~= "" then
        return target .. "?" .. args
    end
    return target
end

local function is_internal_namespace(uri)
    return uri == "/api/projects/internal"
        or uri:find("^/api/projects/internal/") ~= nil
end

local function resolve_target(uri)
    if uri == "/api/projects" or uri:find("^/api/projects/") then
        return append_query(uri)
    end
    if uri == "/api/jobs" or uri:find("^/api/jobs/") then
        return append_query(uri)
    end

    if uri == "/api/admin/projects-info" then
        return append_query("/api/admin/projects-info")
    end

    local transfer_slug = uri:match("^/api/admin/projects/([^/]+)/transfer/?$")
    if transfer_slug then
        return append_query("/api/projects/" .. transfer_slug .. "/transfer")
    end

    local admin_slug = uri:match("^/api/admin/projects/([^/]+)/?$")
    if admin_slug then
        return append_query("/api/projects/" .. admin_slug)
    end

    if uri:find("^/api/platform/pg%-meta/") then
        local meta_slug = uri:match("^/api/platform/pg%-meta/([^/]+)")
        local res = ngx.var.resource
        if not ref_resolver.valid_ref(meta_slug)
            or meta_slug ~= ngx.ctx.studio_request_project_ref
            or type(res) ~= "string"
        then
            return nil, "Canonical pg-meta target is unavailable"
        end
        return append_query(
            "/api/projects/" .. meta_slug .. "/meta" .. res
        )
    end

    local logflare_path = uri:match("^/_internal/logflare/(.*)$")
    if logflare_path then
        return append_query("/api/internal/analytics/" .. logflare_path)
    end

    local internal_slug = uri:match("^/_internal_api/projects/([^/]+)/members$")
    if internal_slug then
        return append_query("/api/projects/" .. internal_slug .. "/members")
    end

    internal_slug = uri:match("^/_internal_api/projects/([^/]+)/rotate%-key$")
    if internal_slug then
        return append_query("/api/projects/" .. internal_slug .. "/rotate-key")
    end

    return nil
end

local function target_for_request(uri)
    if is_internal_namespace(uri) then
        return nil
    end

    local target, target_err = resolve_target(uri)
    if target_err then return nil, target_err end
    if target and is_internal_namespace((target:gsub("%?.*$", ""))) then
        return nil
    end
    return target
end

local function clear_untrusted_internal_headers()
    for _, name in ipairs({
        "X-Internal-Version",
        "X-Internal-Service",
        "X-Internal-Timestamp",
        "X-Internal-Nonce",
        "X-Internal-Signature",
    }) do
        ngx.req.clear_header(name)
    end
end

function M.maybe_sign()
    local uri = ngx.var.uri or ""
    clear_untrusted_internal_headers()

    local target, target_err = target_for_request(uri)
    if target_err then return nil, target_err end
    if not target then
        return true
    end
    if SECRET == "" then
        return nil, "STUDIO_GATEWAY_HMAC_SECRET is not configured"
    end

    return internal_hmac.apply_current_request(SECRET, SERVICE, target)
end

function M.enforce()
    local signed, sign_err = M.maybe_sign()
    if not signed then
        ngx.log(ngx.ERR, "[INTERNAL-HMAC] Falha ao assinar chamada para Projects API: ", sign_err or "unknown")
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.header["Content-Type"] = "application/json; charset=utf-8"
        ngx.say('{"error":"internal_service_signing_failed","message":"Internal service authentication is unavailable"}')
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
    return true
end

-- Exportado apenas para testes de contrato sem precisar simular o proxy inteiro.
M.target_for_request = target_for_request

return M
