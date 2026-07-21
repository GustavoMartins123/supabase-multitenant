local cjson = require("cjson.safe")
local http = require("resty.http")
local outbound_tls = require("utils.outbound_tls")

local API_ORIGIN = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local TOKEN = os.getenv("NGINX_SHARED_TOKEN") or ""

local M = {}

local function request_sync(body)
    if API_ORIGIN == "" then
        return nil, "SERVER_DOMAIN ausente"
    end

    local host = string.match(API_ORIGIN, "//([^/:]+)") or "localhost"
    local httpc = http.new()
    httpc:set_timeout(3000)

    return httpc:request_uri(
        API_ORIGIN .. "/api/projects/internal/users/sync",
        outbound_tls.apply_internal(API_ORIGIN, {
            method = "POST",
            body = body,
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Shared-Token"] = TOKEN,
                ["Host"] = host,
                ["User-Agent"] = "studio-nginx-internal/1.0",
            }
        })
    )
end

function M.sync_user(payload)
    if TOKEN == "" then
        return nil, "NGINX_SHARED_TOKEN ausente"
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
