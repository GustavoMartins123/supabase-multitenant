local cjson = require("cjson.safe")
local http = require("resty.http")

local EXTERNAL_DSN = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local INTERNAL_DSN = (os.getenv("PROJECTS_API_INTERNAL_URL") or ""):gsub("/+$", "")
local TOKEN = os.getenv("NGINX_SHARED_TOKEN") or ""

if INTERNAL_DSN == "" then
    INTERNAL_DSN = "http://projects-api:18000"
end

local M = {}

local function request_sync(origin, body)
    local host = string.match(origin, "//([^/:]+)") or "localhost"
    local httpc = http.new()
    httpc:set_timeout(3000)

    return httpc:request_uri(
        origin .. "/api/projects/internal/users/sync",
        {
            method = "POST",
            body = body,
            ssl_verify = false,
            headers = {
                ["Content-Type"] = "application/json",
                ["X-Shared-Token"] = TOKEN,
                ["Host"] = host,
                ["User-Agent"] = "studio-nginx-internal/1.0",
            }
        }
    )
end

function M.sync_user(payload)
    if TOKEN == "" then
        return nil, "NGINX_SHARED_TOKEN ausente"
    end

    local body = cjson.encode(payload)
    if not body then
        return nil, "falha ao serializar payload"
    end

    local origins = { INTERNAL_DSN }
    if EXTERNAL_DSN ~= "" and EXTERNAL_DSN ~= INTERNAL_DSN then
        table.insert(origins, EXTERNAL_DSN)
    end

    local last_error = nil
    for _, origin in ipairs(origins) do
        local res, err = request_sync(origin, body)
        if res then
            if res.status >= 200 and res.status < 300 then
                local decoded = cjson.decode(res.body or "{}")
                return decoded or true, nil
            end
            return nil, string.format("sync retornou status %s: %s", res.status, res.body or "")
        end
        last_error = err or "falha na requisicao"
    end

    return nil, last_error or "nenhuma origem da API disponivel"
end

return M
