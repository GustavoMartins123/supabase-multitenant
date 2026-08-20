local location = ngx.header["Location"]
if type(location) == "table" then
    location = location[1]
end

if type(location) ~= "string" or location == "" then
    return
end

local suffix = location:match("/storage/v1(/upload/resumable/.+)$")
if not suffix then
    return
end

local origin = ngx.var.studio_public_origin or ""
if origin == "" then
    ngx.log(ngx.ERR, "Origem publica do Studio ausente ao reescrever Location do tus")
    return
end

ngx.header["Location"] = origin .. "/storage/v1" .. suffix
