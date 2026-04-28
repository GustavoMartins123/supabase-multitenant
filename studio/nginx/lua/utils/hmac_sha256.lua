local hmac = require "resty.openssl.hmac"
local str = require "resty.string"

local M = {}

function M.raw(key, message)
    local ctx, err = hmac.new(key, "sha256")
    if not ctx then
        return nil, err
    end

    local digest, final_err = ctx:final(message)
    if not digest then
        return nil, final_err
    end

    return digest
end

function M.hex(key, message)
    local digest, err = M.raw(key, message)
    if not digest then
        return nil, err
    end

    return str.to_hex(digest)
end

return M
