-- Endpoint mantido apenas para compatibilidade com versões antigas da Projects API.
--
-- O namespace atual de snippets usa o UUID estável de projects.id. Portanto,
-- renomear o slug não deve mais alterar diretórios. A migração das pastas antigas
-- acontece sob demanda no proxy de content, usando também project_name_history.
local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")

if ngx.req.get_method() ~= "POST" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local verified, verify_status, verify_err = internal_hmac.verify_current_request(
    os.getenv("PROJECTS_API_HMAC_SECRET") or "",
    "projects-api",
    {
        max_skew = tonumber(os.getenv("INTERNAL_HMAC_MAX_SKEW_SECONDS")) or 60,
    }
)
if not verified then
    ngx.log(
        ngx.WARN,
        "[INTERNAL-HMAC] Snippet migration rejected: ",
        verify_err or "unknown"
    )
    return ngx.exit(verify_status or ngx.HTTP_FORBIDDEN)
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
