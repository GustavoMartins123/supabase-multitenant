local cjson = require("cjson.safe")

-- uri may already be /rest/v1, /graphql/v1 or /storage/v1 after a Lua rewrite.
-- Classify the immutable browser URL, not the internal upstream URL.
local uri = (ngx.var.request_uri or ""):match("^([^?]*)") or ""
local is_api = uri == "/api"
    or uri:sub(1, 5) == "/api/"
    or uri:sub(1, 15) == "/_internal_api/"

if is_api then
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.header.content_type = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(cjson.encode({ error = "authentication required" }))
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local origin = ngx.var.studio_public_origin or ""
local target = origin .. (ngx.var.request_uri or "/")
return ngx.redirect(origin .. "/auth?rd=" .. ngx.escape_uri(target), ngx.HTTP_MOVED_TEMPORARILY)
