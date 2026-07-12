-- Endpoint mantido apenas para compatibilidade com versões antigas da Projects API.
--
-- O namespace atual de snippets usa o UUID estável de projects.id. Portanto,
-- renomear o slug não deve mais alterar diretórios. A migração das pastas antigas
-- acontece sob demanda no proxy de content, usando também project_name_history.
local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local shared_token = require("security.shared_token")

local headers = ngx.req.get_headers()
local supplied_token = headers["X-Shared-Token"] or ""
local internal_service = headers["X-Internal-Service"]

if internal_service ~= "projects-api" or not shared_token.matches(supplied_token) then
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end
if ngx.req.get_method() ~= "POST" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

ngx.req.read_body()
local body = cjson_safe.decode(ngx.req.get_body_data() or "{}") or {}
if type(body.old_name) ~= "string" or type(body.new_name) ~= "string" then
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    renamed = 0,
    errors = setmetatable({}, cjson.array_mt),
    deprecated = true,
    message = "content namespaces are stable and no longer follow project slugs",
}))
