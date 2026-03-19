-- project_db_helper.lua
-- Módulo para buscar funções do projeto via API postgres-meta
-- Usa HTTP em vez de conexão direta ao PostgreSQL

local http = require("resty.http")
local cjson = require("cjson.safe")

local _M = {}

local functions_cache = ngx.shared.service_keys

local SERVER_DOMAIN = os.getenv("SERVER_DOMAIN") or "http://localhost"
local get_service_key = require "get_service_key"

function _M.get_available_functions(project_ref)
    if not project_ref or project_ref == "" or project_ref == "default" then
        ngx.log(ngx.WARN, "[PROJECT-DB] Invalid project_ref: ", project_ref)
        return {}, nil
    end
    
    local cache_key = "functions:" .. project_ref
    local cached = functions_cache:get(cache_key)
    if cached then
        ngx.log(ngx.DEBUG, "[PROJECT-DB] Functions cache hit for: ", project_ref)
        return cjson.decode(cached), nil
    end
    
    local httpc = http.new()
    httpc:set_timeout(10000)
    
    local user_id = ""
    local email = ngx.var.authelia_email or ""
    if email ~= "" then
        local sha256 = require "resty.sha256"
        local str = require "resty.string"
        local h = sha256:new()
        h:update(email:lower():gsub("%s+", ""))
        user_id = str.to_hex(h:final())
    end

    ngx.log(ngx.WARN, "[PROJECT-DB] user_id='", user_id, "' project_ref='", project_ref, "'")

    local url = SERVER_DOMAIN .. "/api/projects/" .. project_ref .. "/functions"
    ngx.log(ngx.INFO, "[PROJECT-DB] Fetching AI functions: ", url)
    
    local res, err = httpc:request_uri(url, {
        method = "GET",
        headers = {
            ["Remote-Email"] = user_id,
            ["Content-Type"] = "application/json"
        },
        ssl_verify = false
    })

    
    if not res then
        ngx.log(ngx.ERR, "[PROJECT-DB] Request failed: ", err)
        return {}, err
    end
    
    ngx.log(ngx.WARN, "[PROJECT-DB] Python status=", res.status, " body=", (res.body or ""):sub(1, 300))

    if res.status ~= 200 then
        ngx.log(ngx.ERR, "[PROJECT-DB] API returned status: ", res.status, " body: ", res.body)
        return {}, "API error: " .. res.status
    end
    
    local functions_data = cjson.decode(res.body)
    if not functions_data then
        ngx.log(ngx.ERR, "[PROJECT-DB] Failed to parse response")
        return {}, "Invalid JSON response"
    end
    
    local AI_TAGS = { "%[AI%]", "@ai%-tool", "@ai[%s:]", "#ai[%s:]", "#ai$" }
    
    local function has_ai_tag(comment)
        if not comment then return false end
        local lower_comment = comment:lower()
        for _, pattern in ipairs(AI_TAGS) do
            if lower_comment:match(pattern:lower()) then
                return true
            end
        end
        return false
    end
    
    local functions = {}
    local skipped = 0
    for _, func in ipairs(functions_data) do
        if func.schema == "public" then
            local comment = func.comment or ""
            
            if has_ai_tag(comment) then
                local clean_desc = comment
                    :gsub("%[AI%]%s*", "")
                    :gsub("@ai%-tool%s*", "")
                    :gsub("@ai%s*", "")
                    :gsub("#ai%s*", "")
                    :gsub("^%s*", "")
                
                if clean_desc == "" then
                    clean_desc = "Função " .. func.name .. " do banco de dados"
                end
                
                local processed = {
                    name = func.name,
                    arguments = func.argument_types or func.args or "",
                    return_type = func.return_type or "unknown",
                    description = clean_desc,
                    id = func.id
                }
                
                processed.parameters = _M.parse_arguments(processed.arguments)
                
                table.insert(functions, processed)
            else
                skipped = skipped + 1
            end
        end
    end
    
    ngx.log(ngx.INFO, "[PROJECT-DB] Found ", #functions, " AI-tagged functions (skipped ", skipped, " without tag)")

    functions_cache:set(cache_key, cjson.encode(functions), 300)
    
    ngx.log(ngx.INFO, "[PROJECT-DB] Found ", #functions, " public functions for project: ", project_ref)
    return functions, nil
end

function _M.parse_arguments(args_str)
    if not args_str or args_str == "" then
        return { type = "object", properties = {} }
    end
    
    local properties = {}
    local required = {}
    
    for arg in string.gmatch(args_str, "([^,]+)") do
        arg = arg:match("^%s*(.-)%s*$")
        
        local name, type_str = arg:match("^([%w_]+)%s+([%w%s]+)")
        
        if name and type_str then
            type_str = type_str:match("^%s*(.-)%s*$")
            
            local json_type = "string"
            
            local type_lower = type_str:lower()
            if type_lower:match("int") or type_lower:match("numeric") or type_lower:match("float") or type_lower:match("double") or type_lower:match("decimal") or type_lower:match("real") or type_lower:match("smallint") or type_lower:match("bigint") then
                json_type = "number"
            elseif type_lower:match("bool") then
                json_type = "boolean"
            elseif type_lower:match("json") then
                json_type = "object"
            end
            
            properties[name] = {
                type = json_type,
                description = "Parâmetro " .. name .. " (" .. type_str .. ")"
            }
            
            if not arg:upper():match("DEFAULT") then
                table.insert(required, name)
            end
        end
    end
    
    return {
        type = "object",
        properties = properties,
        required = #required > 0 and required or nil
    }
end

function _M.functions_to_tools(functions)
    local tools = {}
    
    for _, func in ipairs(functions) do
        local description = func.description
        
        if func.parameters and func.parameters.required and #func.parameters.required > 0 then
            description = description .. " PARÂMETROS OBRIGATÓRIOS: " .. table.concat(func.parameters.required, ", ")
        end
        
        local tool = {
            type = "function",
            ["function"] = {
                name = "db_" .. func.name,
                description = description .. " (retorna: " .. (func.return_type or "unknown") .. ")",
                parameters = func.parameters
            }
        }
        table.insert(tools, tool)
    end
    
    return tools
end

function _M.execute_function(project_ref, func_name, arguments)
    if not project_ref or project_ref == "" or project_ref == "default" then
        return nil, "Invalid project reference"
    end
    
    if func_name:sub(1, 3) == "db_" then
        func_name = func_name:sub(4)
    end
    
    local service_key = get_service_key(project_ref)
    if not service_key or service_key == "" then
        return nil, "No service key available"
    end
    
    local safe_name = func_name:gsub("[^%w_]", "")
    
    local args_list = {}
    if arguments and type(arguments) == "table" then
        if #arguments > 0 then
            for i, v in ipairs(arguments) do
                if type(v) == "string" then
                    table.insert(args_list, "'" .. v:gsub("'", "''") .. "'")
                elseif type(v) == "number" then
                    table.insert(args_list, tostring(v))
                elseif type(v) == "boolean" then
                    table.insert(args_list, v and "true" or "false")
                elseif type(v) == "table" then
                    table.insert(args_list, "'" .. cjson.encode(v):gsub("'", "''") .. "'::jsonb")
                end
            end
        else
            for k, v in pairs(arguments) do
                if type(v) == "string" then
                    table.insert(args_list, "'" .. v:gsub("'", "''") .. "'")
                elseif type(v) == "number" then
                    table.insert(args_list, tostring(v))
                elseif type(v) == "boolean" then
                    table.insert(args_list, v and "true" or "false")
                elseif type(v) == "table" then
                    table.insert(args_list, "'" .. cjson.encode(v):gsub("'", "''") .. "'::jsonb")
                end
            end
        end
    end
    
    local query = string.format(
        "SELECT %s(%s) as result",
        safe_name,
        table.concat(args_list, ", ")
    )
    
    local httpc = http.new()
    httpc:set_timeout(30000)

    local exec_user_id = ""
    local exec_email = ngx.var.authelia_email or ""
    if exec_email ~= "" then
        local sha256 = require "resty.sha256"
        local str = require "resty.string"
        local h = sha256:new()
        h:update(exec_email:lower():gsub("%s+", ""))
        exec_user_id = str.to_hex(h:final())
    end

    local url = SERVER_DOMAIN .. "/api/projects/" .. project_ref .. "/query"
    ngx.log(ngx.INFO, "[PROJECT-DB] Executing query: ", url)
    
    local res, err = httpc:request_uri(url, {
        method = "POST",
        headers = {
            ["Remote-Email"] = exec_user_id,
            ["Content-Type"] = "application/json"
        },
        body = cjson.encode({ query = query }),
        ssl_verify = false
    })
    
    if not res then
        ngx.log(ngx.ERR, "[PROJECT-DB] Query request failed: ", err)
        return nil, err
    end
    
    if res.status ~= 200 then
        ngx.log(ngx.ERR, "[PROJECT-DB] Query returned status: ", res.status, " body: ", res.body)
        return nil, "Query error: " .. (res.body or res.status)
    end
    
    local result = cjson.decode(res.body)
    if not result then
        return nil, "Invalid JSON response"
    end
    
    ngx.log(ngx.INFO, "[PROJECT-DB] Query result: ", cjson.encode(result))
    
    if type(result) == "table" and result[1] then
        return result[1].result or result[1], nil
    end
    
    return result, nil
end

function _M.get_project_context(project_ref, functions)
    if not project_ref or project_ref == "default" then
        return ""
    end
    
    local context = string.format([[

CONTEXTO DO PROJETO:
- Você está trabalhando no projeto: %s
- Banco de dados: _supabase_%s
- Este é um projeto Supabase com todas as extensões padrão habilitadas

]], project_ref, project_ref)
    
    if functions and #functions > 0 then
        context = context .. "FUNÇÕES DISPONÍVEIS NESTE PROJETO:\n"
        context = context .. "Você pode chamar estas funções do schema 'public' diretamente:\n\n"
        
        for i, func in ipairs(functions) do
            if i <= 20 then
                context = context .. string.format(
                    "• %s(%s) → %s\n  %s\n\n",
                    func.name,
                    func.arguments or "",
                    func.return_type or "unknown",
                    func.description or ""
                )
            end
        end
        
        if #functions > 20 then
            context = context .. string.format("... e mais %d funções disponíveis.\n\n", #functions - 20)
        end
        
        context = context .. [[
Para usar estas funções do projeto, chame a tool correspondente com prefixo "db_".
Exemplo: função "minha_funcao" → tool "db_minha_funcao"
]]
    else
        context = context .. "Nenhuma função customizada encontrada no schema 'public' deste projeto.\n"
    end
    
    return context
end

return _M
