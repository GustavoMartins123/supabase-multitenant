local cjson = require("cjson.safe")

local uri = ngx.var.uri or ""
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
