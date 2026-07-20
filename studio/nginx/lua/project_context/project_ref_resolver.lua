local _M = {}

local path_patterns = {
    "^/project/([^/]+)",
    "^/api/platform/props/project/([^/]+)",
    "^/api/platform/projects/([^/]+)",
    "^/api/platform/pg%-meta/([^/]+)",
    "^/api/platform/auth/([^/]+)",
    "^/api/platform/storage/([^/]+)",
    "^/api/v1/projects/([^/]+)",
}

local function valid_ref(ref)
    return type(ref) == "string"
        and ref ~= "default"
        and #ref >= 3
        and #ref <= 40
        and ref:match("^[a-z_][a-z0-9_]*$") ~= nil
end

local function request_path()
    -- request_uri is immutable across internal rewrites and therefore is the
    -- canonical path supplied by this browser request.
    local raw = ngx.var.request_uri or ""
    return raw:match("^([^?]*)") or raw
end

local function ref_from_path(path)
    for _, pattern in ipairs(path_patterns) do
        local ref = (path or ""):match(pattern)
        if ref ~= nil then
            if valid_ref(ref) then
                return ref, true
            end
            return nil, true, "invalid_path_ref"
        end
    end
    return nil, false
end

local function ref_from_header()
    local ref = ngx.var.http_x_studio_project_ref
    if ref == nil or ref == "" then
        return nil
    end
    if not valid_ref(ref) then
        return nil, "invalid_header_ref"
    end
    return ref
end

function _M.resolve()
    local path_ref, has_path_ref, path_err = ref_from_path(request_path())
    if path_err then
        return nil, path_err
    end

    local header_ref, header_err = ref_from_header()
    if header_err then
        return nil, header_err
    end

    if path_ref and header_ref and path_ref ~= header_ref then
        return nil, "project_ref_mismatch"
    end

    local ref = path_ref or header_ref
    if not ref then
        return nil, "project_ref_missing"
    end

    return ref, nil, has_path_ref and "path" or "header"
end

function _M.ref_from_path(path)
    return ref_from_path(path)
end

function _M.valid_ref(ref)
    return valid_ref(ref)
end

return _M
