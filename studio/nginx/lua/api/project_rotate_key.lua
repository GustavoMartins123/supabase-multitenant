local slug = ngx.var.slug

if not slug or slug == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.header.content_type = "application/json"
    ngx.say('{"error":"invalid project"}')
    return
end

ngx.req.read_body()

local req_headers = ngx.req.get_headers()
local res = ngx.location.capture("/_internal_api/projects/" .. slug .. "/rotate-key", {
    method = ngx.HTTP_POST,
    headers = {
        ["Remote-Email"] = req_headers["Remote-Email"],
        ["Remote-Groups"] = req_headers["Remote-Groups"],
    }
})

if res.status == ngx.HTTP_OK then
    ngx.shared.service_keys:delete(slug)
end

ngx.status = res.status
ngx.header.content_type = res.header["Content-Type"] or "application/json"

if res.body and res.body ~= "" then
    ngx.print(res.body)
end
