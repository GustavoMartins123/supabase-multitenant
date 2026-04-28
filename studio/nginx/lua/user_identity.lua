local sha256 = require "resty.sha256"
local str = require "resty.string"

local M = {}

function M.normalize_email(email)
    return (email or ""):lower():gsub("%s+", "")
end

function M.hash_email(email)
    local normalized_email = M.normalize_email(email)
    local hasher = sha256:new()
    hasher:update(normalized_email)
    local digest = hasher:final()
    return str.to_hex(digest)
end

return M
