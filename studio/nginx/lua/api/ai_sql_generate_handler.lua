local cjson = require "cjson.safe"
local ai_generate = require "ai_sql_generate"
local db_helper = require "db_helper"

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

local project_ref = ngx.var.project_ref or "default"
local user_id = ngx.var.authelia_email

local session_id = studio_request.chatId

local db_session_id, err = db_helper.get_or_create_session(user_id, project_ref, session_id)

if err then
    ngx.log(ngx.ERR, "[AI-HANDLER] Erro na sessão: ", err)
    return ngx.exit(500)
end

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
        db_helper.save_message(db_session_id, "user", content, studio_request.model)
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