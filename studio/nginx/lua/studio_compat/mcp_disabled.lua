local cjson = require("cjson.safe")

ngx.status = ngx.HTTP_NOT_IMPLEMENTED
ngx.header["Content-Type"] = "application/json; charset=utf-8"
ngx.header["Cache-Control"] = "no-store"
ngx.say(cjson.encode({
    error = "studio_mcp_requires_project_scoping",
    message = "MCP is disabled until the Studio handler accepts an explicit project ref",
}))
return ngx.exit(ngx.HTTP_NOT_IMPLEMENTED)
