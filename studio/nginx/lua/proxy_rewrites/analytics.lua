-- O Studio self-hosted usa "default" no path; o Logflare precisa do ref selecionado.
local project_ref = ngx.var.project_ref
local uri = ngx.var.uri or ""

if not project_ref
    or project_ref == ""
    or project_ref == "default"
    or not project_ref:match("^[a-z_][a-z0-9_]*$")
    or #project_ref < 3
    or #project_ref > 40
then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say("Projeto nao selecionado para consulta de Analytics")
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
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
