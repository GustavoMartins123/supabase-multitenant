local bit = require "bit"

local expected_token = os.getenv("PUSH_WORKER_TOKEN") or ""
local provided_token = ngx.req.get_headers()["X-Push-Worker-Token"]

local function secure_compare(left, right)
    if not left or not right or #left ~= #right then
        return false
    end

    local diff = 0
    for i = 1, #left do
        diff = bit.bor(diff, bit.bxor(left:byte(i), right:byte(i)))
    end
    return diff == 0
end

if ngx.var.request_method ~= "POST" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.header.content_type = "application/json"
    ngx.say('{"error":"Use POST method"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

if expected_token == "" then
    ngx.log(ngx.ERR, "[PUSH] PUSH_WORKER_TOKEN nao configurado")
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

if not provided_token or provided_token == "" then
    ngx.log(ngx.WARN, "[PUSH] Requisicao sem X-Push-Worker-Token")
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header.content_type = "application/json"
    ngx.say('{"error":"Missing push worker token"}')
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

if not secure_compare(provided_token, expected_token) then
    ngx.log(ngx.WARN, "[PUSH] Token invalido para /api/internal/push")
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.header.content_type = "application/json"
    ngx.say('{"error":"Invalid push worker token"}')
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end
