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

    local host = string.match(API_ORIGIN, "//([^/:]+)") or "localhost"
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

function M.sync_user(payload)
    if HMAC_SECRET == "" then
        return nil, "STUDIO_GATEWAY_HMAC_SECRET ausente"
    end
    if API_ORIGIN == "" then
        return nil, "SERVER_DOMAIN ausente"
    end

    local body = cjson.encode(payload)
    if not body then
        return nil, "falha ao serializar payload"
    end

    local res, err = request_sync(body)
    if not res then
        return nil, err or "falha ao acessar a API por SERVER_DOMAIN"
    end
    if res.status < 200 or res.status >= 300 then
        return nil, string.format("sync retornou status %s: %s", res.status, res.body or "")
    end

    local decoded = cjson.decode(res.body or "{}")
    return decoded or true, nil
end

return M
