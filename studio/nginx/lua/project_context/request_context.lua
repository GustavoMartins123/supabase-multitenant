local resolver = require("project_context.project_ref_resolver")

local _M = {}

local function normalize_expected_ref(ref)
    if ref == nil or ref == "" then
        return nil
    end
    if not resolver.valid_ref(ref) then
        return nil, "invalid_expected_ref"
    end
    return ref
end

local function apply_proxy_context(ref)
    ngx.var.project_ref = ref

    local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
    if server_domain == "" then
        return nil, "server_domain_missing"
    end

    ngx.var.server_path = server_domain .. "/" .. ref .. "/"
    ngx.req.set_header("X-Project-Ref", ref)
    ngx.req.clear_header("X-Studio-Project-Ref")
    return true
end

function _M.capture(expected_ref)
    local expected, expected_err = normalize_expected_ref(expected_ref)
    if expected_err then
        return nil, expected_err
    end

    local existing = ngx.ctx.studio_request_project_ref
    if existing then
        if expected and existing ~= expected then
            return nil, "project_ref_mismatch"
        end
        local applied, apply_err = apply_proxy_context(existing)
        if not applied then
            return nil, apply_err
        end
        return existing
    end

    local ref, resolve_err, source = resolver.resolve()
    if not ref then
        return nil, resolve_err
    end
    if expected and ref ~= expected then
        return nil, "project_ref_mismatch"
    end

    local applied, apply_err = apply_proxy_context(ref)
    if not applied then
        return nil, apply_err
    end

    ngx.ctx.studio_request_project_ref = ref
    ngx.ctx.studio_request_project_ref_source = source
    return ref
end

return _M
