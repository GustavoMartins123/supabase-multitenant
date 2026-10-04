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
    or not ({context=true, schema=true, rows=true, functions=true, execute=true})[action]
    or ngx.var.args and ngx.var.args ~= ""
then return reject(400, "Invalid assistant gateway target") end
local expected_method = (action == "rows" or action == "execute") and "POST" or "GET"
if ngx.req.get_method() ~= expected_method then return reject(405, "Method not allowed") end
if not ngx.req.get_headers()["X-User-Token"] then return reject(401, "User authorization required") end
local target = "/api/projects/" .. ref .. "/assistant/" .. action
local signed = internal_hmac.apply_current_request(os.getenv("STUDIO_GATEWAY_HMAC_SECRET"), "studio-nginx", target)
if not signed then return reject(503, "Assistant gateway signature unavailable") end
ngx.var.assistant_api_target = target
