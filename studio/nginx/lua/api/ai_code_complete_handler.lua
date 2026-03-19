local cjson = require "cjson.safe"
local ai_code = require "ai_code_complete"

ngx.req.read_body()
local body = ngx.req.get_body_data()

if not body or body == "" then
    ngx.header.content_type = "application/json"
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Request body required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local request = cjson.decode(body)
if not request then
    ngx.header.content_type = "application/json"
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Invalid JSON"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if not request.completionMetadata then
    ngx.header.content_type = "application/json"
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "completionMetadata required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

ngx.log(ngx.INFO, "[AI-CODE-COMPLETE] Request from: ", ngx.var.authelia_email)

if ngx.var.project_ref and ngx.var.project_ref ~= "default" then
    request.projectRef = ngx.var.project_ref
end

local result, err = ai_code.complete(
    request, 
    os.getenv("OPENAI_API_KEY"),
    ngx.var.authelia_email,
    os.getenv("OPENAI_API_BASE_URL")
)

ngx.header.content_type = "application/json"

if err then
    ngx.log(ngx.ERR, "[AI-CODE-COMPLETE] Error: ", err)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say(cjson.encode({error = err}))
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

ngx.status = ngx.HTTP_OK
ngx.say(cjson.encode(result))
