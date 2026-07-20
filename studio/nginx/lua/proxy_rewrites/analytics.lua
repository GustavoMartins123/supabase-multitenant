local project_ref = require("project_context.request_context").capture()
local uri = ngx.var.uri or ""

if not project_ref then
    -- The access phase returns the canonical JSON error. Do not invent a
    -- second resolution/error path in rewrite phase.
    return
end

local prefix, suffix = uri:match(
    "^(/api/platform/projects/)[^/]+(/analytics.*)$"
)

if not prefix then
    ngx.log(ngx.ERR, "Rota de Analytics inesperada: ", uri)
    return ngx.exit(ngx.HTTP_NOT_FOUND)
end

local project_uri = prefix .. project_ref .. suffix
ngx.req.set_uri(project_uri, false)
ngx.req.set_header("X-Project-Ref", project_ref)
