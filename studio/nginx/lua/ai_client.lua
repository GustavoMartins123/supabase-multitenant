local http = require("resty.http")
local cjson = require("cjson.safe")

local _M = {}

function _M.parse_base_url(base_url)
    base_url = base_url or "https://openrouter.ai"
    base_url = base_url:gsub("/+$", "")
    local scheme = base_url:match("^(https?)://") or "https"
    local host_part = base_url:gsub("^https?://", "")
    local host, port = host_part:match("^(.+):(%d+)$")
    if not host then
        host = host_part
        port = (scheme == "https") and 443 or 80
    else
        port = tonumber(port)
    end
    return scheme, host, port
end

function _M.connect(httpc, base_url)
    local scheme, host, port = _M.parse_base_url(base_url)

    local ok, err = httpc:connect(host, port)
    if not ok then
        return nil, "Connection failed: " .. (err or "unknown")
    end

    if scheme == "https" then
        local session, err = httpc:ssl_handshake(nil, host, false)
        if not session then
            return nil, "SSL handshake failed: " .. (err or "unknown")
        end
    end

    return true, nil
end

function _M.new_httpc(timeouts)
    local httpc = http.new()
    timeouts = timeouts or {30000, 30000, 120000}
    httpc:set_timeouts(unpack(timeouts))
    return httpc
end

function _M.request(httpc, base_url, api_key, payload)
    local _, ai_host, _ = _M.parse_base_url(base_url)
    return httpc:request({
        path = "/v1/chat/completions",
        method = "POST",
        headers = {
            ["Content-Type"] = "application/json",
            ["Authorization"] = "Bearer " .. api_key,
            ["Host"] = ai_host,
        },
        body = cjson.encode(payload)
    })
end

function _M.filter_think_tags(content)
    if not content or content == "" then return "" end
    local filtered = ""
    local in_think = false
    local i = 1
    local len = #content
    while i <= len do
        if content:sub(i, i + 6) == "<think>" then
            in_think = true
            i = i + 7
        elseif content:sub(i, i + 7) == "</think>" then
            in_think = false
            i = i + 8
        else
            if not in_think then
                filtered = filtered .. content:sub(i, i)
            end
            i = i + 1
        end
    end
    return filtered
end

return _M
