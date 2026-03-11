-- Método deve ser POST para criação
if ngx.var.request_method ~= "POST" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error": "Method not allowed"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

-- Ler body da requisição
ngx.req.read_body()
local body = ngx.req.get_body_data()
if not body then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Request body is required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local cjson = require "cjson.safe"
local user_data = cjson.decode(body)
if not user_data then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Invalid JSON format"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

-- Validar campos obrigatórios
local username = user_data.username
local password = user_data.password  -- Agora recebe senha em texto plano
local display_name = user_data.display_name
local email = user_data.email

if not username or username == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Username is required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if not password or password == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Password is required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if not display_name or display_name == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Display name is required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if not email or email == "" then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Email is required"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

-- Validar formato do email
local email_pat = "^[%w%._%+%-]+@[%w%._%-]+%.[%a%d]+$"
if not email:match(email_pat) then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error":"Invalid email format"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

-- Validar tamanho mínimo da senha
if string.len(password) < 8 then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Password must have at least 8 characters"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

-- FUNÇÃO INTERNA: Gerar hash Argon2 da senha
local function generate_argon2_hash(plain_password)
    -- Gerar salt aleatório de 16 bytes (mesmo que Authelia usa)
    local salt_cmd = "openssl rand -base64 16"
    local salt_handle = io.popen(salt_cmd)
    if not salt_handle then
        ngx.log(ngx.ERR, "[CREATE_USER] Failed to generate salt")
        return nil
    end
    
    local salt_b64 = salt_handle:read("*a")
    salt_handle:close()
    
    if not salt_b64 or salt_b64 == "" then
        ngx.log(ngx.ERR, "[CREATE_USER] Empty salt generated")
        return nil
    end
    
    -- Remover quebras de linha do salt
    salt_b64 = salt_b64:gsub("%s+", "")
    
    local tmp_pass_file = "/tmp/argon2_pass_" .. tostring(ngx.now()) .. "_" .. tostring(math.random(10000, 99999))
    local f_pass = io.open(tmp_pass_file, "w")
    if not f_pass then
        ngx.log(ngx.ERR, "[CREATE_USER] Failed to create temp file for password")
        return nil
    end
    f_pass:write(plain_password)
    f_pass:close()
    
    -- Usar parâmetros exatos do Authelia:
    -- -t 3: time cost (iterações)
    -- -m 16: memory cost (65536 KB = 2^16)
    -- -p 4: parallelism (4 threads)
    -- -l 32: hash length
    -- -e: encoded output
    local cmd = string.format(
        "cat %s | argon2 '%s' -id -t 3 -m 16 -p 4 -l 32 -e; rm -f %s",
        tmp_pass_file,
        salt_b64,
        tmp_pass_file
    )
    
    ngx.log(ngx.ERR, "[CREATE_USER] Generating argon2 hash with Authelia parameters")
    
    local handle = io.popen(cmd)
    if not handle then
        ngx.log(ngx.ERR, "[CREATE_USER] Failed to execute argon2 command")
        os.remove(tmp_pass_file)
        return nil
    end
    
    local output = handle:read("*a")
    local success, exit_code = handle:close()
    os.remove(tmp_pass_file)
    
    if not success then
        ngx.log(ngx.ERR, "[CREATE_USER] Argon2 command failed with exit code: ", tostring(exit_code))
        return nil
    end
    
    if not output or output == "" then
        ngx.log(ngx.ERR, "[CREATE_USER] Argon2 command returned empty output")
        return nil
    end
    
    -- Limpar output (remover quebras de linha)
    local hash = output:gsub("%s+", "")
    
    -- Validar se o hash tem o formato correto e parâmetros do Authelia
    if not hash:match("^%$argon2id%$v=19%$m=65536,t=3,p=4%$") then
        ngx.log(ngx.ERR, "[CREATE_USER] Hash format doesn't match Authelia parameters: ", hash)
        -- Ainda assim retornar o hash se for válido argon2id
        if not hash:match("^%$argon2id%$") then
            return nil
        end
    end
    
    ngx.log(ngx.ERR, "[CREATE_USER] Successfully generated argon2 hash")
    return hash
end

-- Gerar hash da senha
local password_hash = generate_argon2_hash(password)
if not password_hash then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to generate password hash"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Validar se o hash foi gerado corretamente (deve começar com $argon2id$)
if not password_hash:match("^%$argon2id%$") then
    ngx.log(ngx.ERR, "[CREATE_USER] Invalid hash format generated: ", password_hash)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid password hash generated"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Ler arquivo YAML
local lyaml = require "lyaml"
local yaml_path = "/config/users_database.yml"
local f, err = io.open(yaml_path, "r")
if not f then
    ngx.log(ngx.ERR, "[CREATE_USER] Failed to open YAML: ", err)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to read user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local content = f:read("*a")
f:close()

local yaml_data = lyaml.load(content)
if not yaml_data or not yaml_data.users then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid YAML structure"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Verificar se username já existe (case-insensitive)
local username_lower = username:lower()
for existing_user, _ in pairs(yaml_data.users) do
    if existing_user:lower() == username_lower then
        ngx.status = ngx.HTTP_CONFLICT
        ngx.say('{"error": "Username already exists"}')
        return ngx.exit(ngx.HTTP_CONFLICT)
    end
end

-- Verificar se email já existe
local email_lower = email:lower()
for _, user_info in pairs(yaml_data.users) do
    if user_info.email and user_info.email:lower() == email_lower then
        ngx.status = ngx.HTTP_CONFLICT
        ngx.say('{"error": "Email already exists"}')
        return ngx.exit(ngx.HTTP_CONFLICT)
    end
end
local function build_authelia_user(password_hash, email, display_name, is_admin)
    -- `lyaml.null` força o '~' em YAML
    return {
        middle_name    = '',
        email          = email,
        groups         = {"active"},
        family_name    = '',
        nickname       = '',
        gender         = '',
        birthdate      = '',
        website        = '',
        profile        = '',
        picture        = '',
        zoneinfo       = '',
        locale         = '',
        phone_number   = '',
        phone_extension= '',
        disabled       = false,          -- boolean, não string
        password       = password_hash,  -- hash Argon2id
        -- extra          = lyaml.null,             -- tabela vazia → `{}` no YAML
        extra = {
              created_at = "ts:" .. os.date("!%Y-%m-%dT%H:%M:%SZ")
        },
        given_name     = '',
        displayname    = display_name,
        address        = lyaml.null      -- gera "~" (null) no YAML
    }
end

local new_user_record = build_authelia_user(
    password_hash,
    email,
    display_name                     
)
-- Criar novo usuário
yaml_data.users[username] = new_user_record

-- Serializar e salvar YAML
local updated_yaml = lyaml.dump({ yaml_data })

local f_write, err_write = io.open(yaml_path, "w")
if not f_write then
    ngx.log(ngx.ERR, "[CREATE_USER] Failed to write YAML: ", err_write)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to update user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end
f_write:write(updated_yaml)
f_write:close()

-- Gerar ID para cache (hash do username)
local user_id = ngx.md5(username:lower())

-- Adicionar ao cache
local cache = ngx.shared.users_cache
local cache_user = {
    username = username,
    display_name = display_name,
    email = email,
    is_active = true
}
cache:set(user_id, cjson.encode(cache_user))

ngx.log(ngx.ERR, "[CREATE_USER] Successfully created user: ", username)

-- Resposta de sucesso
ngx.status = ngx.HTTP_CREATED
ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    message = "User created successfully",
    user = {
        id = user_id,
        username = username,
        display_name = display_name,
        email = email,
        status = "active"
    },
    timestamp = os.time()
}))
