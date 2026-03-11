local cjson = require "cjson.safe"
local http = require "resty.http"
local pkey = require "resty.openssl.pkey"
local digest = require "resty.openssl.digest"

local function b64url(str)
    local b = ngx.encode_base64(str)
    return b:gsub("+", "-"):gsub("/", "_"):gsub("=", "")
end

local sa_file = io.open("/config/firebase.json", "r")
if not sa_file then
    ngx.status = 500
    ngx.say(cjson.encode({error="firebase.json not found"}))
    return
end
local sa_data = cjson.decode(sa_file:read("*a"))
sa_file:close()

local header = b64url(cjson.encode({alg="RS256", typ="JWT"}))
local now = ngx.time()
local claim = b64url(cjson.encode({
    iss = sa_data.client_email,
    scope = "https://www.googleapis.com/auth/firebase.messaging",
    aud = "https://oauth2.googleapis.com/token",
    exp = now + 3600,
    iat = now
}))

local to_sign = header .. "." .. claim
local pk, err = pkey.new(sa_data.private_key)
if not pk then
    ngx.status = 500
    ngx.say(cjson.encode({error="Invalid private key", detail=err}))
    return
end

local d = digest.new("sha256")
d:update(to_sign)
local sig = pk:sign(d)
local jwt = to_sign .. "." .. b64url(sig)

local httpc = http.new()
local token_res, token_err = httpc:request_uri("https://oauth2.googleapis.com/token", {
    method = "POST",
    body = "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" .. jwt,
    headers = {["Content-Type"] = "application/x-www-form-urlencoded"},
    ssl_verify = false
})

if not token_res or token_res.status ~= 200 then
    ngx.status = 500
    ngx.say(cjson.encode({error="Failed to get access token", detail=token_res and token_res.body or token_err}))
    return
end

local token_data = cjson.decode(token_res.body)
local access_token = token_data.access_token

ngx.req.read_body()
local req_body = cjson.decode(ngx.req.get_body_data())
if not req_body or not req_body.token or not req_body.body then
    ngx.status = 400
    ngx.say(cjson.encode({error="Invalid payload"}))
    return
end

local fcm_payload = cjson.encode({
    message = {
        token = req_body.token,
        notification = {
            title = "Nova Notificação",
            body = req_body.body
        }
    }
})

local fcm_res, fcm_err = httpc:request_uri("https://fcm.googleapis.com/v1/projects/" .. sa_data.project_id .. "/messages:send", {
    method = "POST",
    body = fcm_payload,
    headers = {
        ["Authorization"] = "Bearer " .. access_token,
        ["Content-Type"] = "application/json"
    },
    ssl_verify = false
})

ngx.status = fcm_res and fcm_res.status or 500
ngx.header.content_type = "application/json"
ngx.say(fcm_res and fcm_res.body or cjson.encode({error=fcm_err}))
