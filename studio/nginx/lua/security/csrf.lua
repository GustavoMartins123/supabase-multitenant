local cjson = require("cjson.safe")
local _M = {}

local function reject(status, code)
    ngx.status=status
    ngx.header["Content-Type"]="application/json; charset=utf-8"
    ngx.header["Cache-Control"]="no-store"
    ngx.say(cjson.encode({error=code}))
    return ngx.exit(status)
end

function _M.enforce()
    if ngx.is_subrequest then return true end
    local method=ngx.req.get_method()
    if method=="GET" or method=="HEAD" or method=="OPTIONS" then return true end
    local uri=ngx.var.uri or ""
    if not (uri:find("^/api/") or uri:find("^/storage/v1")) then return true end
    local headers=ngx.req.get_headers()
    -- This endpoint is service-HMAC only and does not authenticate cookies.
    if uri=="/api/internal/push" and not headers.Cookie then return true end
    local file=io.open("/config/.studio-origin", "rb")
    if not file then return reject(503,"canonical_origin_unavailable") end
    local origin=file:read("*a"):gsub("%s+$", "")
    file:close()
    if not origin:match("^https://[^/]+$") then return reject(503,"canonical_origin_invalid") end
    -- Exact origin includes scheme and port. SameSite/CORS are not authorization.
    if headers.Origin~=origin then return reject(403,"csrf_origin_denied") end
    local fetch_site=headers["Sec-Fetch-Site"]
    if fetch_site and fetch_site~="same-origin" then return reject(403,"csrf_fetch_site_denied") end
    return true
end

function _M.require_json()
    local media=tostring(ngx.req.get_headers()["Content-Type"] or ""):lower()
    local base=media:match("^%s*([^;%s]+)")
    if base~="application/json" then return reject(415,"json_content_type_required") end
    return true
end

return _M
