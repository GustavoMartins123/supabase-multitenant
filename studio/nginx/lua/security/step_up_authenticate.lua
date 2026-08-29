local cjson = require("cjson.safe")
local login_session = require("security.login_session")
local step_up_token = require("security.step_up_token")

local MAX_BODY_BYTES = 4096
local HTTP_UNSUPPORTED_MEDIA_TYPE = 415
local UUID_PATTERN = "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$"
local PROJECT_PATTERN = "^[a-z_][a-z0-9_][a-z0-9_][a-z0-9_]*$"
local SLOT_PATTERN = "^[a-z][a-z0-9_-][a-z0-9_-][a-z0-9_-]*$"
local ACTIONS = {
    delete_project = true,
    reveal_secret_key = true,
    create_secret_key = true,
    rotate_secret_key = true,
    activate_secret_key = true,
}

local function respond(status, message)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store, max-age=0"
    ngx.header["Pragma"] = "no-cache"
    ngx.header["X-Content-Type-Options"] = "nosniff"
    ngx.say(cjson.encode({ error = message }))
    return ngx.exit(status)
end

if ngx.req.get_method() ~= "POST" then
    return respond(ngx.HTTP_METHOD_NOT_ALLOWED, "Method not allowed - use POST")
end

local content_type = ngx.var.content_type or ""
local media_type = content_type:match("^%s*([^;]+)")
if not media_type or media_type:lower() ~= "application/json" then
    return respond(HTTP_UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")
end

local content_length = tonumber(ngx.var.http_content_length or "0") or 0
if content_length > MAX_BODY_BYTES then
    return respond(ngx.HTTP_REQUEST_ENTITY_TOO_LARGE, "Request body too large")
end

ngx.req.read_body()
local raw_body = ngx.req.get_body_data()
if not raw_body or raw_body == "" then
    return respond(ngx.HTTP_BAD_REQUEST, "JSON body is required")
end
if #raw_body > MAX_BODY_BYTES then
    return respond(ngx.HTTP_REQUEST_ENTITY_TOO_LARGE, "Request body too large")
end

local body = cjson.decode(raw_body)
raw_body = nil
if type(body) ~= "table" then
    return respond(ngx.HTTP_BAD_REQUEST, "Invalid JSON body")
end
local allowed_fields = {
    password = true,
    action = true,
    project = true,
    resource = true,
}
for field, _ in pairs(body) do
    if not allowed_fields[field] then
        return respond(ngx.HTTP_BAD_REQUEST, "Unexpected field: " .. tostring(field))
    end
end

local password = body.password
local action = body.action
local project = body.project
local resource = body.resource
body.password = nil
if type(password) ~= "string" or password == "" or #password > 1024 then
    return respond(ngx.HTTP_BAD_REQUEST, "Password is required")
end
if type(action) ~= "string" or not ACTIONS[action] then
    return respond(ngx.HTTP_BAD_REQUEST, "Invalid step-up action")
end
if type(project) ~= "string" or #project < 3 or #project > 40
    or not project:match(PROJECT_PATTERN)
then
    return respond(ngx.HTTP_BAD_REQUEST, "Invalid project reference")
end
if type(resource) ~= "string" or resource == "" then
    return respond(ngx.HTTP_BAD_REQUEST, "Invalid step-up resource")
end
if action == "delete_project" and resource ~= project then
    return respond(ngx.HTTP_BAD_REQUEST, "Delete grant must target the project")
end
if action == "create_secret_key" then
    if #resource < 3 or #resource > 40 or not resource:match(SLOT_PATTERN) then
        return respond(ngx.HTTP_BAD_REQUEST, "Invalid API key slot name")
    end
elseif action ~= "delete_project" and not resource:match(UUID_PATTERN) then
    return respond(ngx.HTTP_BAD_REQUEST, "Invalid API key resource")
end

local username = ngx.var.authelia_username or ""
if username == "" then
    return respond(ngx.HTTP_UNAUTHORIZED, "Authenticated Authelia identity unavailable")
end

local authentication_body, encode_err = cjson.encode({
    username = username,
    password = password,
    keepMeLoggedIn = false,
})
password = nil
if not authentication_body then
    ngx.log(ngx.ERR, "[STEP_UP] Failed to encode Authelia request: ", encode_err or "unknown")
    return respond(ngx.HTTP_INTERNAL_SERVER_ERROR, "Step-up authentication unavailable")
end

local auth_response = ngx.location.capture(
    "/internal/authelia-step-up-first-factor",
    { method = ngx.HTTP_POST, body = authentication_body }
)
authentication_body = nil
if not auth_response then
    ngx.log(ngx.ERR, "[STEP_UP] Authelia subrequest returned no response")
    return respond(ngx.HTTP_SERVICE_UNAVAILABLE, "Step-up authentication unavailable")
end
if auth_response.status == ngx.HTTP_TOO_MANY_REQUESTS then
    local retry_after = auth_response.header and auth_response.header["Retry-After"]
    if retry_after then
        ngx.header["Retry-After"] = retry_after
    end
    return respond(ngx.HTTP_TOO_MANY_REQUESTS, "Too many authentication attempts")
end
if auth_response.status == ngx.HTTP_UNAUTHORIZED
    or auth_response.status == ngx.HTTP_FORBIDDEN
then
    return respond(ngx.HTTP_FORBIDDEN, "Senha atual invalida")
end
if auth_response.status ~= ngx.HTTP_OK then
    ngx.log(ngx.ERR, "[STEP_UP] Authelia returned status ", auth_response.status)
    return respond(ngx.HTTP_BAD_GATEWAY, "Step-up authentication unavailable")
end

local auth_result = cjson.decode(auth_response.body or "")
if type(auth_result) ~= "table" or auth_result.status ~= "OK" then
    ngx.log(ngx.ERR, "[STEP_UP] Invalid success response from Authelia")
    return respond(ngx.HTTP_BAD_GATEWAY, "Invalid response from authentication service")
end

local user_id = ngx.var.auth_user_id or ""
local session_fingerprint, fingerprint_err = login_session.fingerprint()
if user_id == "" or not session_fingerprint then
    if fingerprint_err then
        ngx.log(ngx.ERR, "[STEP_UP] Failed to bind login session: ", fingerprint_err)
    end
    return respond(ngx.HTTP_FORBIDDEN, "Current login session cannot be elevated")
end

local token, token_err = step_up_token.sign(
    user_id,
    session_fingerprint,
    action,
    project,
    resource
)
if not token then
    ngx.log(ngx.ERR, "[STEP_UP] Failed to issue grant: ", token_err or "unknown")
    return respond(ngx.HTTP_INTERNAL_SERVER_ERROR, "Step-up grant unavailable")
end

ngx.status = ngx.HTTP_OK
ngx.header["Content-Type"] = "application/json; charset=utf-8"
ngx.header["Cache-Control"] = "no-store, max-age=0"
ngx.header["Pragma"] = "no-cache"
ngx.header["X-Content-Type-Options"] = "nosniff"
ngx.say(cjson.encode({
    step_up_token = token,
    expires_in = step_up_token.TTL_SECONDS,
}))
return ngx.exit(ngx.HTTP_OK)
