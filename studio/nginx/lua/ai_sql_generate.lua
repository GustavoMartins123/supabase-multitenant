local cjson = require("cjson.safe")
local db = require("db_helper")
local project_db = require("project_db_helper")
local ai_client = require("ai_client")

local _M = {}

local function strip_think(s)
    if not s then return s end
    return s:gsub("<think>.-</think>", ""):match("^%s*(.-)%s*$")
end

local function execute_tool(project_ref, tool_name, arguments)
    local args = arguments or {}
    
    local result, err = project_db.execute_function(project_ref, tool_name, args)
    if not result then
        return nil, "Function failed: " .. (err or "unknown")
    end
    return result, nil
end

local function try_parse_tool_call(text)
    if not text or text == "" then
        return nil
    end
    
    if not text:find('"tool_calls"') then
        return nil
    end
    
    local json_start = text:find("{")
    local json_end = text:match(".*()}")
    
    if not json_start or not json_end then
        return nil
    end
    
    local json_str = text:sub(json_start, json_end)
    
    local success, parsed = pcall(cjson.decode, json_str)
    if not success or not parsed.tool_calls then
        return nil
    end
    
    return parsed.tool_calls
end

local function calculate_message_size_kb(msg)
    local content_str = msg.content or ""
    return math.ceil(#content_str / 1024)
end

function _M.generate(studio_request, user_id, project_ref, openai_api_key, openai_model, api_base_url)
    local project_functions = {}
    local project_tools = {}
    if project_ref ~= "default" then
        local funcs, err = project_db.get_available_functions(project_ref)
        if funcs then
            project_functions = funcs
            project_tools = project_db.functions_to_tools(funcs)
        end
    end

    local session_id = ngx.var.cookie_ai_chat_session
    
    local session_id_result, err = db.get_or_create_session(user_id, project_ref, session_id)
    if not session_id_result then
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        ngx.say('{"error": "Database error: ' .. tostring(err) .. '"}')
        return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end

    session_id = session_id_result
    
    if not ngx.var.cookie_ai_chat_session then
        ngx.header["Set-Cookie"] = "ai_chat_session=" .. session_id .. 
            "; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"
    end

    local db_messages, err = db.get_recent_messages(session_id, 8)
    if not db_messages then
        db_messages = {}
    end
    local current_user_message = ""
    local messages = studio_request.messages or {}
    
    if #messages > 0 then
        local last_msg = messages[#messages]
        if last_msg.role and last_msg.parts then
            for _, part in ipairs(last_msg.parts) do
                if part.type == "text" and part.text then
                    current_user_message = current_user_message .. part.text .. "\n"
                end
            end
            current_user_message = current_user_message:gsub("%s+$", "")
        end
    end
    
    if current_user_message == "" then
        ngx.status = ngx.HTTP_BAD_REQUEST
        ngx.say('{"error": "No message content"}')
        return ngx.exit(ngx.HTTP_BAD_REQUEST)
    end

    local user_msg_id, err = db.save_message(session_id, "user", current_user_message, nil)

    local MAX_CONTEXT_KB = 12
    local openai_messages = {}
    
    local base_system_content = [[
        "Você é meu especialista sênior em PostgreSQL e Supabase. "
        "Seu objetivo é me fornecer soluções prontas para produção, "
        "combinando código de alta qualidade com explicações técnicas claras."
        "Eu não quero apenas o código; quero entender o porquê daquela solução."
        "Formato ideal da sua resposta:"
        "- Comece com uma breve explicação técnica sobre a abordagem"
        "- Apresente o código usando blocos markdown"
        "- Adicione comentários sobre performance e segurança"
        "Boas práticas:"
        "- Use qualificação completa do schema (ex: public.usuarios)"
        "- Inclua RETURNING * em INSERT/UPDATE/DELETE"
        "- Use parâmetros ($1, $2) para valores dinâmicos"
        "- Sugira índices apropriados"
        "- Explique a lógica de segurança em políticas RLS"
        "Tópicos: SQL, Design de tabelas, RLS, Edge Functions, Performance"
        "FERRAMENTAS: Se disponíveis, serão listadas no contexto do projeto."]]


    local project_context = project_db.get_project_context(project_ref, project_functions)
    local system_content = base_system_content .. "\n\n" .. project_context

    table.insert(openai_messages, {
        role = "system",
        content = system_content
    })

    for _, msg in ipairs(db_messages) do
        table.insert(openai_messages, {
            role = msg.role,
            content = msg.content
        })
    end
    
    table.insert(openai_messages, {
        role = "user",
        content = current_user_message
    })

    local function calculate_total_kb()
        local total = 0
        for _, msg in ipairs(openai_messages) do
            total = total + calculate_message_size_kb(msg)
        end
        return total
    end

    local current_kb = calculate_total_kb()

    local removed_count = 0
    while current_kb > MAX_CONTEXT_KB and #openai_messages > 2 do
        table.remove(openai_messages, 2)
        removed_count = removed_count + 1
        current_kb = calculate_total_kb()
    end

    if current_kb > MAX_CONTEXT_KB then
        ngx.status = ngx.HTTP_REQUEST_ENTITY_TOO_LARGE
        ngx.say('{"error": "Message too large: ' .. current_kb .. 'KB exceeds limit"}')
        return ngx.exit(ngx.HTTP_REQUEST_ENTITY_TOO_LARGE)
    end

    local all_tools = project_tools

    ngx.log(ngx.WARN, "[AI-GENERATE] Sending ", #all_tools, " tools to AI")
    if #all_tools > 0 then
        ngx.log(ngx.WARN, "[AI-GENERATE] Tools: ", cjson.encode(all_tools))
    end

    local ai_payload = {
        model = openai_model,
        messages = openai_messages,
        temperature = 0.3,
        stream = true
    }
    
    if #all_tools > 0 then
        ai_payload.tools = all_tools
    end

    ngx.header.content_type = "text/event-stream"
    ngx.header.content_length = nil
    ngx.header["Cache-Control"] = "no-cache"
    ngx.header["Connection"] = "keep-alive"
    ngx.header["Access-Control-Allow-Origin"] = "*"
    ngx.header["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

    local httpc = ai_client.new_httpc()

    local ok, err = ai_client.connect(httpc, api_base_url)
    if not ok then
        ngx.say("data: " .. cjson.encode({type = "error", errorText = "AI unavailable"}) .. "\n\n")
        ngx.flush(true)
        return
    end

    local max_iterations = 3
    local iteration = 0
    local final_assistant_response = ""
    local msg_id = "msg-" .. ngx.md5(tostring(ngx.now()))
    local stream_started = false

    while iteration < max_iterations do
        iteration = iteration + 1

        if iteration > 1 then
            httpc:close()
            httpc = ai_client.new_httpc()
            
            local ok, err = ai_client.connect(httpc, api_base_url)
            if not ok then
                ngx.say("data: " .. cjson.encode({type = "error", errorText = "AI reconnection failed"}) .. "\n\n")
                ngx.flush(true)
                return
            end
        end

        local res, err = ai_client.request(httpc, api_base_url, openai_api_key, ai_payload)

        if not res or res.status ~= 200 then
            local status_code = res and res.status or "no_response"
            local err_body = ""
            if res and res.body_reader then
                local chunk = res.body_reader(4096)
                err_body = chunk or ""
            end
            ngx.log(ngx.ERR, "[AI-GENERATE] AI request failed. status=", status_code, " body=", err_body:sub(1, 500))
            ngx.say("data: " .. cjson.encode({type = "error", errorText = "AI error: " .. tostring(status_code)}) .. "\n\n")
            ngx.flush(true)
            httpc:close()
            return
        end

        local started = false
        local buffer = ""
        local assistant_response = ""
        local tool_calls = {}

        local reader = res.body_reader
        
        while true do
            local chunk, err = reader(8192)
            
            if err then
                break
            end
            
            if not chunk then
                break
            end

            buffer = buffer .. chunk
            
            while true do
                local line_end = buffer:find("\n")
                if not line_end then
                    break
                end
                
                local line = buffer:sub(1, line_end - 1):gsub("\r$", "")
                buffer = buffer:sub(line_end + 1)
                
                if line:match("^data: ") then
                    local json_str = line:sub(7)
                    
                    if json_str == "[DONE]" then
                        goto stream_done
                    end
                    
                    local success, stream_data = pcall(cjson.decode, json_str)
                    
                    if success and stream_data.choices and stream_data.choices[1] then
                        local delta = stream_data.choices[1].delta
                        
                        if delta.tool_calls then
                            for _, tc in ipairs(delta.tool_calls) do
                                local idx = tc.index or 0
                                
                                if not tool_calls[idx] then
                                    tool_calls[idx] = {
                                        id = tc.id or "",
                                        type = tc.type or "function",
                                        ["function"] = { name = "", arguments = "" }
                                    }
                                end
                                
                                if tc.id then tool_calls[idx].id = tc.id end
                                if tc.type then tool_calls[idx].type = tc.type end
                                if tc["function"] then
                                    if tc["function"].name then
                                        tool_calls[idx]["function"].name = tc["function"].name
                                    end
                                    if tc["function"].arguments then
                                        tool_calls[idx]["function"].arguments = 
                                            tool_calls[idx]["function"].arguments .. tc["function"].arguments
                                    end
                                end
                            end
                            if not started then
                                stream_started = true
                                started = true
                            end
                        end
                        
                        if delta then
                            if delta.tool_calls then
                                for _, tc in ipairs(delta.tool_calls) do
                                    local idx = tc.index or 0
                                    
                                    if not tool_calls[idx] then
                                        tool_calls[idx] = {
                                            id = tc.id or "",
                                            type = tc.type or "function",
                                            ["function"] = { name = "", arguments = "" }
                                        }
                                    end
                                    
                                    if tc.id then tool_calls[idx].id = tc.id end
                                    if tc.type then tool_calls[idx].type = tc.type end
                                    if tc["function"] then
                                        if tc["function"].name then
                                            tool_calls[idx]["function"].name = tc["function"].name
                                        end
                                        if tc["function"].arguments then
                                            tool_calls[idx]["function"].arguments = 
                                                tool_calls[idx]["function"].arguments .. tc["function"].arguments
                                        end
                                    end
                                end
                                if not started then
                                    stream_started = true
                                    started = true
                                end
                            
                            elseif (delta.content and type(delta.content) == "string") or 
                                   (delta.reasoning_content and type(delta.reasoning_content) == "string") then
                                
                                local content = delta.content or delta.reasoning_content
                                
                                assistant_response = assistant_response .. content
                                
                                local detected_tools = try_parse_tool_call(assistant_response)
                                if detected_tools and #detected_tools > 0 then
                                    for idx, tc in ipairs(detected_tools) do
                                        tool_calls[idx - 1] = tc
                                    end
                                    
                                    if not started then
                                        stream_started = true
                                        started = true
                                    end
                                    
                                    goto continue_stream
                                end
                                
                                local filtered_content = ai_client.filter_think_tags(content)
                                
                                if filtered_content ~= "" then
                                    if not started then
                                        local start_event = {
                                            type = "text-start",
                                            id = msg_id
                                        }
                                        ngx.say("data: " .. cjson.encode(start_event) .. "\n\n")
                                        ngx.flush(true)
                                        started = true
                                        stream_started = true
                                    end
                                    
                                    local delta_event = {
                                        type = "text-delta",
                                        id = msg_id,
                                        delta = filtered_content
                                    }
                                    ngx.say("data: " .. cjson.encode(delta_event) .. "\n\n")
                                    ngx.flush(true)
                                end
                            end
                        end

                        ::continue_stream::
                    end
                end
            end
        end

        ::stream_done::
        
        if assistant_response ~= "" then
            final_assistant_response = final_assistant_response .. assistant_response
        end
        local final_tool_calls_array = {}


        if next(tool_calls) then
            local i = 0
            while tool_calls[i] do
                table.insert(final_tool_calls_array, tool_calls[i])
                i = i + 1
            end
        end

        if next(final_tool_calls_array) then
            table.insert(openai_messages, {
                role = "assistant",
                content = assistant_response ~= "" and assistant_response or nil,
                tool_calls = final_tool_calls_array
            })
            
            for idx, tc in pairs(final_tool_calls_array) do
                local tool_name = tc["function"].name
                local tool_args_str = tc["function"].arguments or ""
                
                tool_args_str = tool_args_str:gsub("<think>[%s%S]-</think>", "")
                tool_args_str = tool_args_str:match("^%s*(.-)%s*$")
                
                local tool_args = {}
                if tool_args_str ~= "" then
                    local success, parsed = pcall(cjson.decode, tool_args_str)
                    if success then
                        tool_args = parsed
                        if type(tool_args) == "table" and not next(tool_args) then
                            tc["function"].arguments = "{}"
                        else
                            tc["function"].arguments = cjson.encode(tool_args)
                        end
                    else
                        ngx.log(ngx.WARN, "[TOOL-CALL] Failed to parse args after strip: '", tool_args_str, "'")
                        tc["function"].arguments = "{}"
                    end
                else
                    tc["function"].arguments = "{}"
                end
                
                local tool_result, tool_err = execute_tool(project_ref, tool_name, tool_args)
                
                if tool_err then
                    tool_result = { error = tool_err }
                end
                
                table.insert(openai_messages, {
                    role = "tool",
                    tool_call_id = tc.id,
                    name = tool_name,
                    content = type(tool_result) == "string" and tool_result or cjson.encode(tool_result)
                })
            end
            
            ai_payload = {
                model = openai_model or "qwen3-coder-next",
                messages = openai_messages,
                temperature = 0.3,
                stream = true
            }
            
        else
            break
        end
    end

    if final_assistant_response ~= "" then
        local ai_msg_id, err = db.save_message(
            session_id, 
            "assistant", 
            final_assistant_response, 
            openai_model or "qwen3-coder-next"
        )
    end

    if stream_started then
        local end_event = {
            type = "text-end",
            id = msg_id
        }
        ngx.say("data: " .. cjson.encode(end_event) .. "\n\n")
        ngx.flush(true)
    else
        ngx.say("data: " .. cjson.encode({type = "error", errorText = "No response"}) .. "\n\n")
        ngx.flush(true)
    end

    httpc:set_keepalive(10000, 100)
end

return _M
