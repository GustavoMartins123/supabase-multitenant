local secure_compare = require("security.secure_compare")
local file_store = require("admin_api.authelia_file_store")
local lfs = require("lfs")
local _M = {}
local CONSUMED = "/config/.studio-bootstrap-consumed"

function _M.closed(users)
    local marker, err, errno = lfs.symlinkattributes(CONSUMED)
    if marker then return true end
    if errno ~= 2 then error("Installation state unavailable: " .. tostring(err)) end
    -- Existing installations are never reopened by disabling/deleting an admin.
    for username in pairs(users) do
        if username ~= "__bootstrap_placeholder__" then return true end
    end
    return false
end

function _M.verify(users, supplied)
    if _M.closed(users) then return nil, "Installation bootstrap is permanently closed", 403 end
    local path = os.getenv("STUDIO_BOOTSTRAP_TOKEN_FILE")
    if not path or path == "" then return nil, "Installation proof is not configured", 503 end
    local file = io.open(path, "rb")
    if not file then return nil, "Installation proof is unavailable", 503 end
    local expected = file:read("*a"):gsub("%s+$", "")
    file:close()
    if #expected < 43 then return nil, "Invalid installation proof configuration", 503 end
    if type(supplied) ~= "string" or not secure_compare.equals(expected, supplied) then
        return nil, "Valid installation proof required", 403
    end
    return true
end

function _M.consume()
    -- Caller holds the users_database lock. Persist BEFORE any account write,
    -- so a crash or API failure cannot reopen this anonymous privilege boundary.
    return file_store.atomic_write(CONSUMED, "consumed\n", 384)
end

return _M
