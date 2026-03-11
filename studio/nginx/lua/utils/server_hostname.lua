local full_url = ngx.var.server_domain
if not full_url or full_url == "" then
    return "" 
end
local hostname = string.match(full_url, "https?://([^/:]+)")
return hostname or full_url
