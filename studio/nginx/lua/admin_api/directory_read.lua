local cjson = require("cjson.safe")
local hmac = require("security.internal_hmac")
local sha = require("security.hmac_sha256")
local secret = os.getenv("PROJECTS_API_HMAC_SECRET") or ""
if ngx.req.get_method() ~= "GET" then return ngx.exit(405) end
local verified, status = hmac.verify_current_request(secret, "projects-api")
if not verified then return ngx.exit(status) end
local snapshot, err = require("admin_api.authelia_user_store").with_lock(function()
    return require("admin_api.directory_snapshot").read_locked(true)
end)
if not snapshot then
    ngx.log(ngx.ERR, "[DIRECTORY] Canonical snapshot unavailable: ", err)
    return ngx.exit(503)
end
local body = cjson.encode(snapshot)
local signature = sha.hex(secret, "studio-directory-v1\n" .. ngx.req.get_headers()["X-Internal-Nonce"] .. "\n" .. body)
if not signature then return ngx.exit(503) end
ngx.header["X-Directory-Signature"] = signature
ngx.header["Cache-Control"] = "no-store"
ngx.header.content_type = "application/json"
ngx.print(body)
