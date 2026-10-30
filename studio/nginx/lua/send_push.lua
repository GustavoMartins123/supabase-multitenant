local cjson = require("cjson.safe")
local oauth = require("push.oauth")
local lock = require("resty.lock")
local outbound_tls = require("utils.outbound_tls")

local function respond(status, payload, retry_after)
    ngx.status = status
    ngx.header.content_type = "application/json"
    if retry_after then ngx.header["Retry-After"] = retry_after end
    ngx.say(type(payload)=="string" and payload or cjson.encode(payload))
end

ngx.req.read_body()
local raw = ngx.req.get_body_data()
local req = raw and cjson.decode(raw)
if type(req) ~= "table" or type(req.token) ~= "string" or req.token=="" or #req.token>4096
    or type(req.body) ~= "string" or type(req.project) ~= "string" or req.project==""
    or #req.project>128 or not req.project:match("^[%w_%-]+$") then
    respond(400, {push_category="INVALID_REQUEST"})
    return
end
local delivery_key = req.idempotency_key
if type(delivery_key) ~= "string" or #delivery_key>128
    or not delivery_key:match("^[%w_%-]+$") then
    respond(400, {push_category="INVALID_REQUEST"})
    return
end
-- project never chooses a DB, filesystem path or Firebase identity. Hash the
-- actual request as well as the operation key to prevent cache aliasing.
local cache_key = oauth.hash(req.project .. "\0" .. delivery_key .. "\0" .. req.token .. "\0" .. req.body)
local cache = ngx.shared.push_idempotency
if not cache or not ngx.shared.push_locks then
    respond(500, {push_category="AUTH_ERROR"})
    return
end
local cached = cache:get(cache_key)
if cached then respond(200, cached); return end
local mutex = lock:new("push_locks", {timeout=5, exptime=oauth.lock_expiry(2)+5})
local acquired = mutex and mutex:lock("delivery:" .. cache_key)
if not acquired then respond(503, {push_category="TEMPORARY_FAILURE"}, "5"); return end

local function deliver()
    cached = cache:get(cache_key)
    if cached then return 200, cached end
    local file = io.open("/config/firebase.json", "r")
    if not file then return 500, {push_category="AUTH_ERROR"} end
    local sa = cjson.decode(file:read("*a"))
    file:close()
    if type(sa) ~= "table" or type(sa.client_email) ~= "string" or type(sa.private_key) ~= "string"
        or type(sa.project_id) ~= "string" or not sa.project_id:match("^[%w%-]+$") then
        return 500, {push_category="AUTH_ERROR"}
    end
    local access, category, retry = oauth.get(sa)
    if not access then return category=="AUTH_ERROR" and 502 or 503, {push_category=category}, retry end
    local fcm_url = "https://fcm.googleapis.com/v1/projects/" .. sa.project_id .. "/messages:send"
    local res = oauth.client():request_uri(fcm_url, outbound_tls.apply_public(fcm_url, {
        method="POST",
        body=cjson.encode({message={token=req.token, notification={title="Nova Notificação", body=req.body}}}),
        headers={["Authorization"]="Bearer " .. access, ["Content-Type"]="application/json"},
    }))
    if not res then return 502, {push_category="NETWORK_FAILURE"} end
    local retry_after = res.headers and (res.headers["Retry-After"] or res.headers["retry-after"])
    if res.status>=200 and res.status<300 then
        -- FCM success contains only the message name; never reflect tokens.
        local data = cjson.decode(res.body)
        local body = cjson.encode({name=type(data)=="table" and data.name or nil})
        local ttl = tonumber(os.getenv("PUSH_IDEMPOTENCY_TTL_SECONDS")) or 86400
        if ttl<=0 then ttl=86400 end
        local stored = cache:safe_set(cache_key, body, ttl)
        if not stored then ngx.log(ngx.WARN, "[PUSH] success cache capacity exhausted") end
        return res.status, body
    end
    if res.status==401 then oauth.invalidate(sa, access) end
    local data = cjson.decode(res.body)
    local error = type(data)=="table" and data.error
    local details = {}
    if type(error)=="table" and type(error.details)=="table" then
        for _, detail in ipairs(error.details) do
            if type(detail)=="table" and detail["@type"]=="type.googleapis.com/google.firebase.fcm.v1.FcmError" then
                local code = detail.errorCode
                if code=="UNREGISTERED" or code=="INVALID_ARGUMENT" or code=="SENDER_ID_MISMATCH"
                    or code=="THIRD_PARTY_AUTH_ERROR" or code=="QUOTA_EXCEEDED" or code=="UNAVAILABLE" or code=="INTERNAL" then
                    details[#details+1] = {["@type"]=detail["@type"], errorCode=code}
                end
            end
        end
    end
    return res.status, {error={code=res.status, details=details}}, retry_after
end

local ok, status, payload, retry_after = pcall(deliver)
mutex:unlock()
if not ok then
    ngx.log(ngx.ERR, "[PUSH] delivery failed internally")
    respond(500, {push_category="AUTH_ERROR"})
    return
end
respond(status, payload, retry_after)
