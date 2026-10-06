local cjson = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")
local hmac = require("security.hmac_sha256")
local random = require("resty.random")
local str = require("resty.string")

local function reject(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json"
    ngx.say(cjson.encode({ message = message }))
    return ngx.exit(status)
end

if ngx.var.args and ngx.var.args ~= "" then return reject(400, "Assistant routes do not accept query parameters") end
local method = ngx.req.get_method()
if method ~= "GET" and method ~= "PUT" and method ~= "POST" then return reject(405, "Method not allowed") end
if method ~= "GET" then require("security.csrf").require_json() end
local body, body_err = internal_hmac.read_current_body()
if not body then return reject(400, "Invalid assistant request body") end
local requested_ref
if body ~= "" then
    local decoded = cjson.decode(body)
    if type(decoded) ~= "table" then return reject(400, "Invalid JSON") end
    requested_ref = decoded.projectRef
end
local context = require("security.project_access").enforce(requested_ref)
if type(context) ~= "table" then return end
local file = io.open(os.getenv("ASSISTANT_GATEWAY_KEY_FILE"), "rb")
if not file then return reject(503, "Assistant authentication unavailable") end
local secret = file:read("*a"):gsub("%s+$", "")
file:close()
if #secret ~= 64 or not secret:match("^[0-9a-f]+$") then return reject(503, "Assistant authentication unavailable") end
local nonce = random.bytes(16, true)
if not nonce then return reject(503, "Assistant authentication unavailable") end
local body_hash = internal_hmac.sha256_hex(body)
if not body_hash then return reject(503, "Assistant authentication unavailable") end
local proof = cjson.encode({
    userId = ngx.var.auth_user_id, projectId = context.project_uuid, ref = context.ref,
    role = context.role, userToken = ngx.var.auth_user_token,
    timestamp = ngx.time(), nonce = str.to_hex(nonce), method = method,
    target = ngx.var.request_uri, bodyHash = body_hash,
})
if not proof then return reject(503, "Assistant authentication unavailable") end
local encoded = ngx.encode_base64(proof):gsub("%+", "-"):gsub("/", "_"):gsub("=+$", "")
local signature = hmac.hex(secret, encoded)
if not signature then return reject(503, "Assistant authentication unavailable") end
ngx.req.set_header("X-Assistant-Context", encoded .. "." .. signature)
ngx.req.clear_header("Cookie")
ngx.req.clear_header("Authorization")
ngx.req.clear_header("X-User-Token")
