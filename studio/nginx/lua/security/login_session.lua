local digest = require("resty.openssl.digest")

local M = {}

local function sha256_bin(value)
    local ctx, err = digest.new("sha256")
    if not ctx then
        return nil, err
    end

    local ok, update_err = ctx:update(value)
    if not ok then
        return nil, update_err
    end

    return ctx:final()
end

function M.fingerprint()
    local session_cookie = ngx.var.cookie_authelia_session or ""
    if session_cookie == "" then
        return nil, nil
    end

    local hash, err = sha256_bin(session_cookie)
    if not hash then
        return nil, err or "failed to hash login session"
    end

    return (ngx.encode_base64(hash)
        :gsub("%+", "-")
        :gsub("/", "_")
        :gsub("=+$", "")), nil
end

return M
