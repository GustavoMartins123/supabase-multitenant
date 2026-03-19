local cjson = require("cjson.safe")
local project_db = require("project_db_helper")
local ai_client = require("ai_client")

local _M = {}

local DEFAULT_MODEL = os.getenv("OPENAI_MODEL") or "qwen3-coder-next"

local function get_code_context(project_ref, completion_metadata)
    local context = ""
    
    if project_ref and project_ref ~= "" and project_ref ~= "default" then
        local funcs, err = project_db.get_available_functions(project_ref)
        if funcs and #funcs > 0 then
            context = context .. "-- Projeto: " .. project_ref .. "\n"
            context = context .. "-- Funções disponíveis no schema 'public':\n"
            for _, func in ipairs(funcs) do
                context = context .. string.format("-- %s(%s) → %s\n", 
                    func.name, 
                    func.arguments or "", 
                    func.return_type or "unknown"
                )
            end
            context = context .. "\n"
        end
    end
    
    local lang = completion_metadata.language or "pgsql"
    if lang == "pgsql" then
        context = context .. "-- Linguagem: PostgreSQL/Supabase\n"
        context = context .. "-- Use boas práticas: qualificação de schema, índices, RLS, RETURNING *\n\n"
    end
    
    return context
end

function _M.complete(request, api_key, user_email, api_base_url)
    local project_ref = request.projectRef or "default"
    local completion_metadata = request.completionMetadata or {}
    
    local text_before = completion_metadata.textBeforeCursor or ""
    local text_after = completion_metadata.textAfterCursor or ""
    local prompt = completion_metadata.prompt or ""
    local selection = completion_metadata.selection or ""
    local language = completion_metadata.language or "pgsql"
    
    local code_context = get_code_context(project_ref, completion_metadata)
    
    local system_content = [[
Você é um assistente especialista em PostgreSQL e Supabase.
Sua tarefa é gerar código SQL de alta qualidade baseado no contexto e prompt do usuário.

REGRAS:
- Gere APENAS código SQL, sem explicações
- Use qualificação completa de schema (ex: public.tabela)
- Inclua comentários SQL quando necessário
- Use boas práticas de performance e segurança
- Se for criar tabelas, inclua índices apropriados
- Para INSERT/UPDATE/DELETE, use RETURNING *
- Considere RLS (Row Level Security) quando aplicável

FORMATO DA RESPOSTA:
- Retorne APENAS o código SQL
- Não use blocos markdown, retorne o SQL puro
- Não inclua explicações antes ou depois
]]
    
    if code_context ~= "" then
        system_content = system_content .. "\nCONTEXTO DO PROJETO:\n" .. code_context
    end
    
    local user_content = ""
    
    if prompt ~= "" then
        user_content = prompt
    else
        if text_before ~= "" or text_after ~= "" then
            user_content = "Complete o código SQL seguinte:\n\n"
            if text_before ~= "" then
                user_content = user_content .. text_before
            end
            user_content = user_content .. "[COMPLETE AQUI]"
            if text_after ~= "" then
                user_content = user_content .. text_after
            end
        end
    end
    
    if selection ~= "" then
        user_content = user_content .. "\n\nTexto selecionado:\n" .. selection
    end
    
    if user_content == "" then
        return nil, "No prompt or context provided"
    end
    
    local ai_payload = {
        model = DEFAULT_MODEL,
        messages = {
            { role = "system", content = system_content },
            { role = "user", content = user_content }
        },
        temperature = 0.2,
        stream = false,
        max_tokens = 4096
    }
    
    local httpc = ai_client.new_httpc()
    
    local ok, err = ai_client.connect(httpc, api_base_url)
    if not ok then
        return nil, "AI unavailable"
    end
    
    local res, err = ai_client.request(httpc, api_base_url, api_key, ai_payload)
    
    if not res then
        httpc:close()
        return nil, "AI request failed"
    end
    
    local body = res:read_body()
    httpc:set_keepalive(10000, 100)
    
    if res.status ~= 200 then
        return nil, "AI API error: " .. res.status
    end
    
    local response_data = cjson.decode(body)
    if not response_data then
        return nil, "Invalid AI response"
    end
    
    local content = ""
    if response_data.choices and response_data.choices[1] then
        local message = response_data.choices[1].message
        if message and message.content then
            content = message.content
        end
    end
    
    return ai_client.filter_think_tags(content), nil
end

return _M