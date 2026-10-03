local M = {}

M.verify_internal = true

local function hostname(url)
    return tostring(url or ""):match("^https?://%[([^%]]+)%]")
        or tostring(url or ""):match("^https?://([^/:]+)")
end

function M.backend_name()
    local origin = os.getenv("SERVER_DOMAIN")
    local host = hostname(origin)
    assert(host and host ~= "", "SERVER_DOMAIN must specify the backend origin")
    if origin:match("^https://") and (host:match("^%d+%.%d+%.%d+%.%d+$") or host:find(":", 1, true)) then
        local name = os.getenv("STUDIO_BACKEND_TLS_NAME")
        assert(name and name:match("^[%a][%w%-]*%.[%w%.%-]+$"), "STUDIO_BACKEND_TLS_NAME must specify the backend DNS certificate identity")
        return name
    end
    return host
end

function M.apply_internal(url, options)
    options = options or {}
    options.ssl_verify = M.verify_internal
    if tostring(url or ""):match("^https://") then
        local configured_verify = os.getenv("SERVICE_KEY_VERIFY_TLS")
        assert(configured_verify == "true", "SERVICE_KEY_VERIFY_TLS must remain enabled for HTTPS")
        options.ssl_server_name = hostname(url)
        if tostring(url):match("^https://[^/]+") == os.getenv("SERVER_DOMAIN") then
            options.ssl_server_name = M.backend_name()
        end
    end
    return options
end

function M.apply_public(url, options)
    options = options or {}
    options.ssl_verify = true
    options.ssl_server_name = hostname(url)
    return options
end

return M
