local cjson = require("cjson.safe")
local ai_generate = require("ai_sql_generate")
local user_identity = require("project_context.user_identity")

ngx.req.read_body()
local body = ngx.req.get_body_data()

if not body or body == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Request body required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local studio_request = cjson.decode(body)
if not studio_request then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Invalid JSON"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local resolver = require("project_context.project_ref_resolver")
local requested_ref = studio_request.projectRef
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
local project_ref = context.ref
studio_request.projectRef = project_ref
local function current_user_id()
    local email = user_identity.normalize_email(ngx.var.authelia_email or "")
    if email == "" then
        return ""
    end

    local cache = ngx.shared.users_cache
    return (cache and cache:get("email:" .. email)) or ""
end

local user_id = current_user_id()
if user_id == "" then
    ngx.status = ngx.HTTP_UNAUTHORIZED
    ngx.say('{"error": "User identity not found"}')
    return ngx.exit(ngx.HTTP_UNAUTHORIZED)
end

local client_chat_id = studio_request.chatId
if client_chat_id ~= nil then
    local normalized = tostring(client_chat_id):lower()
    local a, b, c, d, e = normalized:match(
        "^([0-9a-f]+)%-([0-9a-f]+)%-([0-9a-f]+)%-([0-9a-f]+)%-([0-9a-f]+)$"
    )
    if not a or #a ~= 8 or #b ~= 4 or #c ~= 4 or #d ~= 4 or #e ~= 12 then
        ngx.status = ngx.HTTP_BAD_REQUEST
        ngx.header.content_type = "application/json"
        ngx.say('{"error": "Invalid chatId"}')
        return ngx.exit(ngx.HTTP_BAD_REQUEST)
    end
    client_chat_id = normalized
else
    client_chat_id = "default"
end

local session_hash = ngx.md5(user_id .. ":" .. project_ref .. ":" .. client_chat_id)
studio_request.chatId = session_hash:sub(1, 8)
    .. "-" .. session_hash:sub(9, 12)
    .. "-" .. session_hash:sub(13, 16)
    .. "-" .. session_hash:sub(17, 20)
    .. "-" .. session_hash:sub(21, 32)

local messages = studio_request.messages
if messages and #messages > 0 then
    local last_message = messages[#messages]
    if last_message.role == "user" then
        local content = ""
        if last_message.parts then
            for _, part in ipairs(last_message.parts) do
                if part.type == "text" and part.text then
                    content = content .. part.text
                end
            end
        end
    end
end

ai_generate.generate(
    studio_request,
    user_id,
    project_ref,
    os.getenv("OPENAI_API_KEY"),
    os.getenv("OPENAI_MODEL"),
    os.getenv("OPENAI_API_BASE_URL")
)
