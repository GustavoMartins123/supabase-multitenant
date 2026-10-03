local cjson = require("cjson.safe")
local http = require("resty.http")
local internal_hmac = require("security.internal_hmac")
local outbound_tls = require("utils.outbound_tls")

local API_ORIGIN = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local HMAC_SECRET = os.getenv("STUDIO_GATEWAY_HMAC_SECRET") or ""
local TARGET = "/api/projects/internal/users/sync"

local M = {}

local function request_sync(body)
    if API_ORIGIN == "" then
        return nil, "SERVER_DOMAIN ausente"
    end

    local signed_headers, sign_err = internal_hmac.sign_headers(
        HMAC_SECRET,
        "studio-nginx",
        "POST",
        TARGET,
        body
    )
    if not signed_headers then
        return nil, sign_err or "falha ao assinar sync interno"
    end

    local host = string.match(API_ORIGIN, "^https?://([^/]+)$")
    if not host then return nil, "SERVER_DOMAIN must be a canonical HTTP origin" end
    local headers = {
        ["Content-Type"] = "application/json",
        ["Host"] = host,
        ["User-Agent"] = "studio-nginx-internal/2.0",
    }
    for name, value in pairs(signed_headers) do
        headers[name] = value
    end

    local httpc = http.new()
    httpc:set_timeout(3000)
    return httpc:request_uri(
        API_ORIGIN .. TARGET,
        outbound_tls.apply_internal(API_ORIGIN, {
            method = "POST",
            body = body,
            headers = headers,
        })
    )
end

function M.sync_directory()
    -- All callers hold users_database.yml's lock through the API transaction.
    local snapshot, snapshot_err = require("admin_api.directory_snapshot").read_locked(true)
    if not snapshot then return nil, snapshot_err end
    local body, encode_err = cjson.encode(snapshot)
    if not body then return nil, encode_err end
    local res, err = request_sync(body)
    if not res then return nil, err end
    if res.status ~= 200 then return nil, "directory sync rejected: " .. tostring(res.status) end
    local decoded = cjson.decode(res.body)
    if type(decoded) ~= "table" or decoded.revision ~= snapshot.revision then return nil, "invalid directory acknowledgement" end
    return decoded
end

function M.sync_user(payload)
    local directory, err = M.sync_directory()
    if not directory then return nil, err end
    for _, user in ipairs(directory.users or {}) do
        if user.id == payload.id then return user end
    end
    return nil, "user absent from confirmed directory"
end

return M
