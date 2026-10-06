local cjson = require("cjson.safe")
local internal_hmac = require("security.internal_hmac")
local function reject(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json"
    ngx.say(cjson.encode({ message = message }))
    return ngx.exit(status)
end
local file = io.open(os.getenv("ASSISTANT_GATEWAY_KEY_FILE"), "rb")
if not file then return reject(503, "Assistant gateway unavailable") end
local secret = file:read("*a"):gsub("%s+$", "")
file:close()
local ok, status = internal_hmac.verify_current_request(secret, "studio-assistant")
if not ok then return reject(status, "Assistant gateway authentication failed") end
local ref, action = ngx.var.uri:match("^/_internal/assistant/([a-z]+)/([a-z]+)$")
if not require("project_context.project_ref_resolver").valid_ref(ref)
    or not ({context=true, schema=true, security=true, rows=true, functions=true, execute=true, sql=true, privileges=true})[action]
    or ngx.var.args and ngx.var.args ~= ""
then return reject(400, "Invalid assistant gateway target") end
local expected_method = (action == "security" or action == "rows" or action == "execute" or action == "sql" or action == "privileges") and "POST" or "GET"
if ngx.req.get_method() ~= expected_method then return reject(405, "Method not allowed") end
local user_token = ngx.req.get_headers()["X-Assistant-User-Token"]
if type(user_token) ~= "string" or #user_token < 50 or #user_token > 4096 then
    return reject(401, "User authorization required")
end
ngx.req.set_header("X-User-Token", user_token)
ngx.req.clear_header("X-Assistant-User-Token")
local target = "/api/projects/" .. ref .. "/assistant/" .. action
local signed = internal_hmac.apply_current_request(os.getenv("STUDIO_GATEWAY_HMAC_SECRET"), "studio-nginx", target)
if not signed then return reject(503, "Assistant gateway signature unavailable") end
ngx.req.clear_header("X-Assistant-Execution-Proof")
if action == "sql" or action == "privileges" then
    local signature = ngx.req.get_headers()["X-Internal-Signature"]
    local proof = require("security.hmac_sha256").hex(os.getenv("STUDIO_GATEWAY_HMAC_SECRET"),
        "assistant-" .. action .. "-execution-v1\n" .. signature .. "\n" .. user_token)
    if not proof then return reject(503, "Assistant execution proof unavailable") end
    ngx.req.set_header("X-Assistant-Execution-Proof", proof)
end
ngx.var.assistant_api_target = target
