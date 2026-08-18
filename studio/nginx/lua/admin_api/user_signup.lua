if ngx.var.request_method ~= "POST" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error": "Method not allowed"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

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
local user_store = require("admin_api.authelia_user_store")
local user_sync = require("admin_api.user_sync")

local user_data = cjson.decode(body)
body = nil
if not user_data then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error": "Invalid JSON format"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local username = user_data.username
local password = user_data.password
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

local email_pat = "^[%w%._%+%-]+@[%w%._%-]+%.[%a%d]+$"
if not email:match(email_pat) then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say('{"error":"Invalid email format"}')
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local normalized_email = user_identity.normalize_email(email)
local min_password_length = is_bootstrap_admin and 12 or 8
if string.len(password) < min_password_length then
    ngx.status = ngx.HTTP_BAD_REQUEST
    ngx.say(cjson.encode({
        error = "Password must have at least " .. tostring(min_password_length) .. " characters"
    }))
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

local function generate_argon2_hash(plain_password)
    ngx.log(ngx.INFO, "[CREATE_USER] Generating argon2 hash with Authelia parameters")
    local hash = argon2_password.hash_password(plain_password)
    if not hash then
        return nil
    end
    if not hash:match("^%$argon2id%$v=19%$m=65536,t=3,p=4%$")
        and not hash:match("^%$argon2id%$")
    then
        return nil
    end
    return hash
end

-- O hash e caro; faz fora do lock. Validacoes contra o snapshot atual do YAML
-- sao repetidas dentro do lock antes de qualquer escrita.
local password_hash = generate_argon2_hash(password)
user_data.password = nil
password = nil
if not password_hash then
    ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
    ngx.say('{"error": "Failed to generate password hash"}')
    return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
end

local function is_bootstrap_placeholder(existing_username)
    return existing_username == "__bootstrap_placeholder__"
end

local function users_have_admin(users)
    for existing_username, user_info in pairs(users or {}) do
        if user_info.disabled ~= true and not is_bootstrap_placeholder(existing_username) then
            for _, group in ipairs(user_info.groups or {}) do
                if group == "admin" then
                    return true
                end
            end
        end
    end
    return false
end

local function build_authelia_user(hash, user_email, name, is_admin)
    local lyaml = require("lyaml")
    local groups = { "active" }
    if is_admin then
        table.insert(groups, "admin")
    end
    return {
        middle_name = "",
        email = user_email,
        groups = groups,
        family_name = "",
        nickname = "",
        gender = "",
        birthdate = "",
        website = "",
        profile = "",
        picture = "",
        zoneinfo = "",
        locale = "",
        phone_number = "",
        phone_extension = "",
        disabled = false,
        password = hash,
        extra = {
            created_at = "ts:" .. os.date("!%Y-%m-%dT%H:%M:%SZ")
        },
        given_name = "",
        displayname = name,
        address = lyaml.null
    }
end

local function error_result(status, message)
    return {
        status = status,
        payload = { error = message }
    }
end

local result, mutation_err = user_store.with_lock(function()
    -- Releitura obrigatoria dentro do lock: nenhum snapshot obtido antes do
    -- lock pode participar de uma mutacao.
    local yaml_data, original, load_err = user_store.load()
    if not yaml_data then
        ngx.log(ngx.ERR, "[CREATE_USER] Failed to read YAML: ", load_err)
        return error_result(ngx.HTTP_INTERNAL_SERVER_ERROR, "Failed to read user database")
    end

    if is_bootstrap_admin and users_have_admin(yaml_data.users) then
        return error_result(ngx.HTTP_FORBIDDEN, "Initial admin already exists")
    end

    local username_lower = username:lower()
    for existing_user, user_info in pairs(yaml_data.users) do
        if not is_bootstrap_placeholder(existing_user)
            and existing_user:lower() == username_lower
        then
            return error_result(ngx.HTTP_CONFLICT, "Username already exists")
        end
        if not is_bootstrap_placeholder(existing_user)
            and user_info.email
            and user_info.email:lower() == normalized_email
        then
            return error_result(ngx.HTTP_CONFLICT, "Email already exists")
        end
    end

    -- Ordem global de locks em todos os caminhos: users_database.yml -> ids.yml.
    -- O init_worker segue a mesma ordem; nenhum caminho adquire na ordem inversa.
    local authelia_user_id, _, identifier_err =
        authelia_identifiers.ensure_identifier(username)
    if not authelia_user_id then
        ngx.log(
            ngx.ERR,
            "[CREATE_USER] Failed to generate/export Authelia identifier: ",
            identifier_err
        )
        local status = tostring(identifier_err or ""):find("busy", 1, true)
            and ngx.HTTP_SERVICE_UNAVAILABLE
            or ngx.HTTP_INTERNAL_SERVER_ERROR
        return error_result(status, "Failed to generate Authelia opaque identifier")
    end

    local new_user_record = build_authelia_user(
        password_hash,
        email,
        display_name,
        is_bootstrap_admin
    )

    if is_bootstrap_admin then
        for existing_user in pairs(yaml_data.users) do
            if is_bootstrap_placeholder(existing_user) then
                yaml_data.users[existing_user] = nil
            end
        end
    end
    yaml_data.users[username] = new_user_record

    local written, write_err = user_store.write(yaml_data)
    if not written then
        ngx.log(ngx.ERR, "[CREATE_USER] Failed to write YAML: ", write_err)
        return error_result(
            ngx.HTTP_INTERNAL_SERVER_ERROR,
            "Failed to update user database"
        )
    end

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
        local restored, restore_err = user_store.restore(original)
        if not restored then
            ngx.log(
                ngx.CRIT,
                "[CREATE_USER] Failed to rollback users database after sync error: ",
                restore_err
            )
            return error_result(
                ngx.HTTP_INTERNAL_SERVER_ERROR,
                "User synchronization failed and Authelia rollback also failed"
            )
        end
        return error_result(
            ngx.HTTP_BAD_GATEWAY,
            "User created in Authelia but failed to sync with backend"
        )
    end

    local canonical_id = authelia_user_id
    if type(sync_result) == "table" and sync_result.id then
        canonical_id = sync_result.id
    end

    -- Cache e YAML mudam sob o mesmo lock. Assim uma ativacao/desativacao
    -- concorrente nao pode ser sobrescrita depois por um cache atrasado.
    local cache = ngx.shared.users_cache
    local cache_user = {
        username = username,
        display_name = display_name,
        email = normalized_email,
        user_uuid = canonical_id,
        is_active = true,
        is_admin = is_bootstrap_admin
    }
    local encoded = cjson.encode(cache_user)
    if encoded then
        cache:set(canonical_id, encoded)
        cache:set("email:" .. normalized_email, canonical_id)
    end

    return {
        status = ngx.HTTP_CREATED,
        payload = {
            message = is_bootstrap_admin
                and "Initial admin created successfully"
                or "User created successfully",
            user = {
                id = canonical_id,
                username = username,
                display_name = display_name,
                email = email,
                status = "active",
                is_admin = is_bootstrap_admin
            },
            timestamp = os.time()
        }
    }
end)

if not result then
    ngx.log(ngx.ERR, "[CREATE_USER] Authelia mutation failed: ", mutation_err)
    local status = tostring(mutation_err or ""):find("busy", 1, true)
        and ngx.HTTP_SERVICE_UNAVAILABLE
        or ngx.HTTP_INTERNAL_SERVER_ERROR
    result = error_result(status, mutation_err or "Failed to update user database")
end

ngx.status = result.status
ngx.header.content_type = "application/json"
if result.status == ngx.HTTP_SERVICE_UNAVAILABLE then
    ngx.header["Retry-After"] = "1"
end
ngx.say(cjson.encode(result.payload))
return ngx.exit(result.status)
