package.path = "studio/nginx/lua/?.lua;studio/nginx/lua/?/init.lua;" .. package.path

local verifier_ok = false
local verifier_status = 401
local verifier_error = "Missing internal signature"

package.loaded["security.internal_hmac"] = {
    verify_current_request = function(secret, service, options)
        assert(service == "studio-server")
        if verifier_ok then
            return true
        end
        return nil, verifier_status, verifier_error
    end,
}

local request = {
    method = "GET",
    headers = {},
    cleared = {},
}

_G.ngx = {
    HTTP_NOT_FOUND = 404,
    HTTP_NOT_ALLOWED = 405,
    HTTP_BAD_REQUEST = 400,
    HTTP_UNAUTHORIZED = 401,
    var = {
        uri = "/_internal/logflare/api/endpoints/query/logs",
        args = "project=test",
    },
    req = {
        get_method = function()
            return request.method
        end,
        get_headers = function()
            return request.headers
        end,
        clear_header = function(name)
            request.cleared[name] = true
            request.headers[name] = nil
            request.headers[string.lower(name)] = nil
        end,
    },
    shared = {
        internal_hmac_nonces = {},
    },
}

local guard = require("security.logflare_internal_guard")

-- Direct request without HMAC must fail at the edge.
local ok, status, code = guard.check()
assert(ok == nil)
assert(status == 401)
assert(code == "analytics_internal_auth_failed")

-- Unknown paths are rejected before any upstream proxying.
ngx.var.uri = "/_internal/logflare/api/anything"
ok, status, code = guard.check()
assert(ok == nil)
assert(status == 404)
assert(code == "analytics_path_not_allowed")

-- Method/path combinations are explicit.
ngx.var.uri = "/_internal/logflare/api/sources"
request.method = "POST"
ok, status, code, _, allow = guard.check()
assert(ok == nil)
assert(status == 405)
assert(code == "analytics_method_not_allowed")
assert(allow == "GET")

-- A valid Studio HMAC is accepted and sensitive caller headers are removed.
ngx.var.uri = "/_internal/logflare/api/backends"
ngx.var.args = nil
request.method = "GET"
request.headers = {
    Authorization = "Bearer must-not-cross",
    ["X-API-KEY"] = "must-not-cross",
    Cookie = "session=must-not-cross",
}
request.cleared = {}
verifier_ok = true
ok, status = guard.check()
assert(ok == true)
assert(status == nil)
assert(request.cleared.Authorization == true)
assert(request.cleared["X-API-KEY"] == true)
assert(request.cleared.Cookie == true)

-- Mutations require a bounded JSON body with Content-Length.
ngx.var.uri = "/_internal/logflare/api/backends"
request.method = "POST"
request.headers = { ["Content-Type"] = "application/json" }
verifier_ok = true
ok, status, code = guard.check()
assert(ok == nil)
assert(status == 411)
assert(code == "analytics_content_length_required")

request.headers["Content-Length"] = tostring(256 * 1024 + 1)
ok, status, code = guard.check()
assert(ok == nil)
assert(status == 413)
assert(code == "analytics_body_too_large")

print("logflare internal guard runtime: ok")
