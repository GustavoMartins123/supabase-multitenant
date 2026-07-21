local M = {}

local raw = (os.getenv("SERVICE_KEY_VERIFY_TLS") or "true"):lower()
M.verify_internal = raw ~= "0" and raw ~= "false" and raw ~= "no" and raw ~= "off"

local function hostname(url)
    return tostring(url or ""):match("^https?://%[([^%]]+)%]")
        or tostring(url or ""):match("^https?://([^/:]+)")
end

function M.apply_internal(url, options)
    options = options or {}
    options.ssl_verify = M.verify_internal
    if tostring(url or ""):match("^https://") then
        options.ssl_server_name = hostname(url)
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
