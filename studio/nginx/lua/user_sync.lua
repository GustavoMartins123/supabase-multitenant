local cjson = require "cjson.safe"
local http = require "resty.http"

local DSN = os.getenv("SERVER_DOMAIN") or ""
local TOKEN = os.getenv("NGINX_SHARED_TOKEN") or ""
local HOST = string.match(DSN, "//([^/:]+)") or "localhost"

local M = {}

function M.sync_user(payload)
    if DSN == "" or TOKEN == "" then
        return nil, "SERVER_DOMAIN ou NGINX_SHARED_TOKEN ausente"
    end

    local httpc = http.new()
    httpc:set_timeout(2000)

    local body = cjson.encode(payload)
    if not body then
        return nil, "falha ao serializar payload"
    end

    local res, err = httpc:request_uri(
        DSN .. "/api/projects/internal/users/sync",
        {
            method = "POST",
            body = body,
            ssl_verify = false,
            keepalive = true,
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Shared-Token"] = TOKEN,
                ["Host"] = HOST,
            }
        }
    )

    if not res then
        return nil, err or "falha na requisicao"
    end

    if res.status < 200 or res.status >= 300 then
        return nil, string.format("sync retornou status %s: %s", res.status, res.body or "")
    end

    local decoded = cjson.decode(res.body or "{}")
    return decoded or true, nil
end

return M
