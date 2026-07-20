-- The tenant prefix is already carried by server_path.
ngx.req.set_uri("graphql/v1", false)
