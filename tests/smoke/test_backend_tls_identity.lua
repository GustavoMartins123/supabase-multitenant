package.path = "studio/nginx/lua/?.lua;" .. package.path
local env = {
    SERVER_DOMAIN = "https://192.0.2.10",
    STUDIO_BACKEND_TLS_NAME = "supabase-backend.internal",
    SERVICE_KEY_VERIFY_TLS = "true",
}
os.getenv = function(name) return env[name] end
local tls = require("utils.outbound_tls")

local options = tls.apply_internal("https://192.0.2.10/api/projects", {})
assert(options.ssl_verify == true)
assert(options.ssl_server_name == "supabase-backend.internal")
env.STUDIO_BACKEND_TLS_NAME = nil
assert(not pcall(tls.apply_internal, "https://192.0.2.10/api/projects", {}))
env.STUDIO_BACKEND_TLS_NAME = "192.0.2.10"
assert(not pcall(tls.apply_internal, "https://192.0.2.10/api/projects", {}))
env.STUDIO_BACKEND_TLS_NAME = "supabase-backend.internal"
env.SERVICE_KEY_VERIFY_TLS = "false"
assert(not pcall(tls.apply_internal, "https://192.0.2.10/api/projects", {}))
env.SERVICE_KEY_VERIFY_TLS = "true"
env.SERVER_DOMAIN = "https://backend.example.test"
options = tls.apply_internal("https://backend.example.test/api/projects", {})
assert(options.ssl_server_name == "backend.example.test")
options = tls.apply_internal("https://authelia:9091/api/authz", {})
assert(options.ssl_server_name == "authelia")
options = tls.apply_public("https://public.example.test/path", {})
assert(options.ssl_verify == true and options.ssl_server_name == "public.example.test")
print("Backend TLS identity: IP transport, explicit peer identity and fail-closed policy passed")
