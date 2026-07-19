local cjson = require("cjson.safe")
local ai_code = require("ai_code_complete")

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

local resolver = require("project_context.project_ref_resolver")
local requested_ref = request.projectRef
local tab_ref = resolver.resolve()
if requested_ref ~= nil and not resolver.valid_ref(requested_ref) then
    ngx.header.content_type = "application/json"
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Invalid projectRef"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end
if requested_ref == nil then
    requested_ref = tab_ref
end
if resolver.is_slug_mode()
    and resolver.valid_ref(tab_ref)
    and requested_ref ~= tab_ref
then
    ngx.header.content_type = "application/json"
    ngx.status = ngx.HTTP_CONFLICT
    ngx.say('{"error": "projectRef does not match the current tab"}')
    return ngx.exit(ngx.HTTP_CONFLICT)
end
local context = require("security.project_access").enforce(requested_ref)
if type(context) ~= "table" then
    return
end
request.projectRef = context.ref

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
