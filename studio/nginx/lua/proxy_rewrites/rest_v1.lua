local rest_path = ngx.var[1] or ""
rest_path = rest_path:gsub("^/", "")

-- O upstream PostgREST espera o prefixo removido pela rota pública do Studio.
ngx.var.target_rest_path = "/rest/v1/" .. rest_path
ngx.req.set_uri("/rest/v1/" .. rest_path, false)
