local internal_hmac = require("security.internal_hmac")

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

local function target_for_request(uri)
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

    local meta_slug, meta_resource = uri:match(
        "^/api/platform/pg%-meta/([a-z_][a-z0-9_]*)(/.*)$"
    )
    if not meta_slug then
        meta_slug = uri:match(
            "^/api/platform/pg%-meta/([a-z_][a-z0-9_]*)/?$"
        )
        meta_resource = ""
    end
    if meta_slug then
        return append_query(
            "/api/projects/" .. meta_slug .. "/meta" .. (meta_resource or "")
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
    local target = target_for_request(uri)
    if not target then
        return true
    end
    if SECRET == "" then
        return nil, "STUDIO_GATEWAY_HMAC_SECRET is not configured"
    end

    clear_untrusted_internal_headers()
    return internal_hmac.apply_current_request(SECRET, SERVICE, target)
end

-- Exportado apenas para testes de contrato sem precisar simular o proxy inteiro.
M.target_for_request = target_for_request

return M
