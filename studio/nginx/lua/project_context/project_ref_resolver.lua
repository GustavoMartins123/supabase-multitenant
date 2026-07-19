local _M = {}

local hmac_sha256 = require("security.hmac_sha256")
local secure_compare = require("security.secure_compare")

local context_mode = (os.getenv("STUDIO_PROJECT_CONTEXT_MODE") or "slug"):lower()
if context_mode ~= "slug"
    and context_mode ~= "hybrid"
    and context_mode ~= "cookie"
then
    context_mode = "slug"
end

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

local function ref_from_path(path)
    for _, pattern in ipairs(path_patterns) do
        local ref = (path or ""):match(pattern)
        if ref ~= nil then
            if valid_ref(ref) then
                return ref, true, ref
            end
            -- Um path com ref explicito nunca pode cair no Referer ou cookie.
            return nil, true, ref
        end
    end
    return nil, false, nil
end

local function ref_from_same_origin_referer()
    local referer = ngx.var.http_referer or ""
    local scheme, authority, path = referer:match("^(https?)://([^/]+)(/[^?#]*)")
    if not scheme or not authority or not path then
        return nil
    end

    local request_scheme = (ngx.var.scheme or ""):lower()
    local request_authority = ngx.var.http_host or ""
    if scheme:lower() ~= request_scheme
        or authority:lower() ~= request_authority:lower()
    then
        return nil
    end
    local ref = ref_from_path(path)
    return ref
end

local function should_log_invalid_cookie()
    local uri = ngx.var.uri or ""
    return not (
        uri == "/auth"
        or uri:match("^/auth/")
        or uri == "/login"
        or uri == "/logout"
    )
end

local function resolve_cookie()
    local cookie = ngx.var.cookie_supabase_project
    if not cookie then
        return "default"
    end

    local ref, ts, sig = cookie:match("^([^%.]+)%.(%d+)%.([0-9a-f]+)$")
    if not ref then
        if should_log_invalid_cookie() then
            ngx.log(ngx.WARN, "Cookie de projeto malformado; limpando cookie")
        end
        return "default"
    end

    if not valid_ref(ref) then
        if should_log_invalid_cookie() then
            ngx.log(ngx.WARN, "Project ref invalido no cookie; limpando cookie")
        end
        return "default"
    end

    local numeric_ts = tonumber(ts)
    if not numeric_ts then
        return "default"
    end

    local cookie_age = ngx.time() - numeric_ts
    local max_age = 604800
    if cookie_age < 0 or cookie_age > max_age then
        if should_log_invalid_cookie() then
            ngx.log(ngx.INFO, "Cookie de projeto expirado para projeto: ", ref)
        end
        return "default"
    end

    local expect, err = hmac_sha256.hex(COOKIE_SECRET, ref .. "." .. ts)
    if not expect then
        ngx.log(ngx.ERR, "Falha ao validar cookie de projeto: ", err)
        return "default"
    end
    if not secure_compare.equals(expect, sig) then
        if should_log_invalid_cookie() then
            ngx.log(ngx.WARN, "Assinatura de cookie invalida para projeto: ", ref,
                    "; limpando cookie")
        end
        return "default"
    end

    local renewal_threshold = 518400
    if cookie_age > renewal_threshold then
        local new_ts = tostring(ngx.time())
        local new_sig, renewal_err = hmac_sha256.hex(
            COOKIE_SECRET,
            ref .. "." .. new_ts
        )
        if not new_sig then
            ngx.log(ngx.ERR, "Falha ao renovar cookie de projeto: ", renewal_err)
            return ref
        end

        ngx.header["Set-Cookie"] =
            ("supabase_project=%s.%s.%s; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=%d")
            :format(ref, new_ts, new_sig, max_age)
    end

    return ref
end

function _M.resolve()
    if context_mode == "slug" then
        local path_ref, has_path_ref = ref_from_path(ngx.var.uri)
        if has_path_ref then
            return path_ref or "default"
        end
        return ref_from_same_origin_referer() or "default"
    end

    if context_mode == "hybrid" then
        local path_ref, has_path_ref, raw_path_ref = ref_from_path(ngx.var.uri)
        if has_path_ref then
            -- Excecao de rollback estritamente para o marcador legado. Outros
            -- refs invalidos explicitos continuam falhando sem fallback.
            if raw_path_ref == "default" then
                return resolve_cookie()
            end
            return path_ref or "default"
        end
        return ref_from_same_origin_referer() or resolve_cookie()
    end

    return resolve_cookie()
end

function _M.is_slug_mode()
    return context_mode == "slug"
end

function _M.valid_ref(ref)
    return valid_ref(ref)
end

return _M
