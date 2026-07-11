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

local cjson = require("cjson.safe")
local argon2_password = require("security.argon2_password")
local user_identity = require("project_context.user_identity")
local authelia_identifiers = require("admin_api.authelia_identifiers")
local user_sync = require("admin_api.user_sync")
local user_data = cjson.decode(body)
body = nil
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
local is_bootstrap_admin = ngx.var.bootstrap_admin == "true"

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

local normalized_email = user_identity.normalize_email(email)

-- Validar tamanho mínimo da senha
local min_password_length = is_bootstrap_admin and 12 or 8
if string.len(password) < min_password_length then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say(cjson.encode({
        error = "Password must have at least " .. tostring(min_password_length) .. " characters"
    }))
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

-- FUNÇÃO INTERNA: Gerar hash Argon2 da senha
local function generate_argon2_hash(plain_password)
    -- Usar parâmetros exatos do Authelia:
    -- -t 3: time cost (iterações)
    -- m=65536: memory cost em KiB
    -- -p 4: parallelism (4 threads)
    -- hash length 32 bytes
    ngx.log(ngx.ERR, "[CREATE_USER] Generating argon2 hash with Authelia parameters")

    local hash = argon2_password.hash_password(plain_password)
    if not hash then
        return nil
    end

    -- Validar se o hash tem o formato correto e parâmetros do Authelia
    if not hash:match("^%$argon2id%$v=19%$m=65536,t=3,p=4%$") then
        ngx.log(ngx.ERR, "[CREATE_USER] Hash format doesn't match Authelia parameters")
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
user_data.password = nil
password = nil
if not password_hash then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to generate password hash"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Validar se o hash foi gerado corretamente (deve começar com $argon2id$)
if not password_hash:match("^%$argon2id%$") then
    ngx.log(ngx.ERR, "[CREATE_USER] Invalid hash format generated")
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid password hash generated"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Ler arquivo YAML
local lyaml = require("lyaml")
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
if type(yaml_data) ~= "table" then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Invalid YAML structure"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end
yaml_data.users = yaml_data.users or {}

local original_yaml_data = lyaml.load(content)

local function is_bootstrap_placeholder(username, user_info)
    return username == "__bootstrap_placeholder__"
end

local function users_have_admin(users)
    for username, user_info in pairs(users or {}) do
        if user_info.disabled ~= true and not is_bootstrap_placeholder(username, user_info) then
            for _, group in ipairs(user_info.groups or {}) do
                if group == "admin" then
                    return true
                end
            end
        end
    end
    return false
end

if is_bootstrap_admin and users_have_admin(yaml_data.users) then
    ngx.status = ngx.HTTP_FORBIDDEN
    ngx.say('{"error": "Initial admin already exists"}')
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

-- Verificar se username já existe (case-insensitive)
local username_lower = username:lower()
for existing_user, user_info in pairs(yaml_data.users) do
    if not is_bootstrap_placeholder(existing_user, user_info) and existing_user:lower() == username_lower then
        ngx.status = ngx.HTTP_CONFLICT
        ngx.say('{"error": "Username already exists"}')
        return ngx.exit(ngx.HTTP_CONFLICT)
    end
end

-- Verificar se email já existe
local email_lower = normalized_email
for existing_user, user_info in pairs(yaml_data.users) do
    if not is_bootstrap_placeholder(existing_user, user_info) and user_info.email and user_info.email:lower() == email_lower then
        ngx.status = ngx.HTTP_CONFLICT
        ngx.say('{"error": "Email already exists"}')
        return ngx.exit(ngx.HTTP_CONFLICT)
    end
end
local function build_authelia_user(password_hash, email, display_name, is_admin)
    local groups = {"active"}
    if is_admin then
        table.insert(groups, "admin")
    end

    -- `lyaml.null` força o '~' em YAML
    return {
        middle_name    = '',
        email          = email,
        groups         = groups,
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

local function write_yaml_file(path, data)
    local serialized = lyaml.dump({ data })
    local handle, write_err = io.open(path, "w")
    if not handle then
        return nil, write_err
    end
    handle:write(serialized)
    handle:close()
    return true
end

local authelia_user_id, created_identifier, identifier_err = authelia_identifiers.ensure_identifier(username)
if not authelia_user_id then
    ngx.log(ngx.ERR, "[CREATE_USER] Failed to generate/export Authelia identifier: ", identifier_err)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to generate Authelia opaque identifier"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local new_user_record = build_authelia_user(
    password_hash,
    email,
    display_name,
    is_bootstrap_admin
)

if is_bootstrap_admin then
    for existing_user, user_info in pairs(yaml_data.users) do
        if is_bootstrap_placeholder(existing_user, user_info) then
            yaml_data.users[existing_user] = nil
        end
    end
end

-- Criar novo usuário
yaml_data.users[username] = new_user_record

-- Serializar e salvar YAML
local ok_write, err_write = write_yaml_file(yaml_path, yaml_data)
if not ok_write then
    ngx.log(ngx.ERR, "[CREATE_USER] Failed to write YAML: ", err_write)
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to update user database"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

-- Adicionar ao cache
local cache = ngx.shared.users_cache
local cache_user = {
    username = username,
    display_name = display_name,
    email = normalized_email,
    user_uuid = authelia_user_id,
    is_active = true,
    is_admin = is_bootstrap_admin
}
local encoded_cache_user = cjson.encode(cache_user)
cache:set(authelia_user_id, encoded_cache_user)
cache:set("email:" .. normalized_email, authelia_user_id)

local sync_result, sync_err = user_sync.sync_user({
    id = authelia_user_id,
    username = username,
    display_name = display_name,
    groups = new_user_record.groups,
    is_active = true,
    source = is_bootstrap_admin and "studio_bootstrap" or "studio_admin"
})

if sync_err then
    ngx.log(ngx.ERR, "[CREATE_USER] Failed to sync user with backend: ", sync_err)
    if type(original_yaml_data) == "table" then
        write_yaml_file(yaml_path, original_yaml_data)
    else
        yaml_data.users[username] = nil
        write_yaml_file(yaml_path, yaml_data)
    end
    cache:delete(authelia_user_id)
    cache:delete("email:" .. normalized_email)
    ngx.status = ngx.HTTP_BAD_GATEWAY
    ngx.say('{"error": "User created in Authelia but failed to sync with backend"}')
    return ngx.exit(ngx.HTTP_BAD_GATEWAY)
end

if sync_result and sync_result.id then
    cache_user.user_uuid = sync_result.id
    local encoded = cjson.encode(cache_user)
    cache:set(sync_result.id, encoded)
    cache:set("email:" .. normalized_email, sync_result.id)
end

ngx.log(ngx.ERR, "[CREATE_USER] Successfully created user: ", username)

-- Resposta de sucesso
ngx.status = ngx.HTTP_CREATED
ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    message = is_bootstrap_admin and "Initial admin created successfully" or "User created successfully",
    user = {
        id = sync_result and sync_result.id or authelia_user_id,
        username = username,
        display_name = display_name,
        email = email,
        status = "active",
        is_admin = is_bootstrap_admin
    },
    timestamp = os.time()
}))
