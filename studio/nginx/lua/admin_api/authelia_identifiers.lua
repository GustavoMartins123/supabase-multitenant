local lyaml = require("lyaml")
local shell = require("resty.shell")
local file_store = require("admin_api.authelia_file_store")

local IDS_PATH = "/config/ids.yml"
local CONFIG_PATH = "/config/configuration.runtime.yml"
local AUTHELIA_BIN = "/usr/local/bin/authelia"
local OPENID_SERVICE = "openid"
local COMMAND_TIMEOUT_MS = 10000
local IDS_LOCK = "ids.yml"
local FILE_MODE = 438 -- 0666

local M = {}

local function trim(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function read_document()
    local handle, err = io.open(IDS_PATH, "rb")
    if not handle then
        return nil, "ids.yml indisponivel ou vazio; execute a configuracao canonica"
    end

    local content = handle:read("*a") or ""
    handle:close()

    if content:gsub("%s+", "") == "" then
        return nil, "ids.yml indisponivel ou vazio; execute a configuracao canonica"
    end

    local ok, document = pcall(lyaml.load, content)
    if not ok or type(document) ~= "table" then
        return nil, "ids.yml invalido"
    end

    if type(document.identifiers) ~= "table" then
        return nil, "ids.yml sem lista de identifiers"
    end

    return document, nil
end

local function write_document(document)
    local ok, serialized = pcall(lyaml.dump, { document })
    if not ok or type(serialized) ~= "string" then
        return nil, serialized or "falha ao serializar ids.yml"
    end
    return file_store.atomic_write(IDS_PATH, serialized, FILE_MODE)
end

local function is_safe_username(username)
    return username:match("^[%w._@%-]+$") ~= nil
end

local function run_authelia_command(args)
    local ok, stdout, stderr, reason, status =
        shell.run(args, nil, COMMAND_TIMEOUT_MS, 65536)
    if ok and status == 0 then
        return true, stdout
    end

    return nil, string.format(
        "authelia command failed status=%s reason=%s stderr=%s stdout=%s",
        tostring(status),
        tostring(reason),
        tostring(stderr or ""),
        tostring(stdout or "")
    )
end

local function export_identifiers()
    local tmp_path = string.format(
        "%s.tmp.%s.%s",
        IDS_PATH,
        tostring(ngx.worker.pid()),
        tostring(math.floor(ngx.now() * 1000000))
    )
    os.remove(tmp_path)

    local ok, err = run_authelia_command({
        AUTHELIA_BIN,
        "storage",
        "user",
        "identifiers",
        "export",
        "--config",
        CONFIG_PATH,
        "--file",
        tmp_path,
    })
    if not ok then
        os.remove(tmp_path)
        return nil, err
    end

    local mode_ok, mode_err = file_store.chmod(tmp_path, FILE_MODE)
    if not mode_ok then
        os.remove(tmp_path)
        return nil, mode_err
    end

    local renamed, rename_err = os.rename(tmp_path, IDS_PATH)
    if not renamed then
        os.remove(tmp_path)
        return nil, rename_err
    end

    return true
end

local function generate_identifier(username)
    if not is_safe_username(username) then
        return nil, "username contem caracteres invalidos para gerar opaque identifier"
    end

    local ok, err = run_authelia_command({
        AUTHELIA_BIN,
        "storage",
        "user",
        "identifiers",
        "generate",
        "--config",
        CONFIG_PATH,
        "--users",
        username,
        "--services",
        OPENID_SERVICE,
        "--sectors",
        "",
    })
    if not ok then
        return nil, err
    end

    return export_identifiers()
end

local function index_document(document)
    local identifiers, identity_owners = {}, {}
    local count = 0
    for index in pairs(document.identifiers) do
        count = count + 1
        if type(index) ~= "number" or index % 1 ~= 0 or index < 1 or index > #document.identifiers then
            return nil, "ids.yml identifiers deve ser uma lista densa"
        end
    end
    if count ~= #document.identifiers then return nil, "ids.yml identifiers deve ser uma lista densa" end
    for _, entry in ipairs(document.identifiers) do
        if type(entry) ~= "table" then return nil, "entrada invalida em ids.yml" end
        if entry.service == OPENID_SERVICE then
            if type(entry.username) ~= "string" or type(entry.identifier) ~= "string" then
                return nil, "identidade openid invalida"
            end
            local username, identifier = trim(entry.username), trim(entry.identifier)
            if username == "" or not is_safe_username(username) or identifier == ""
                or identifiers[username] or identity_owners[identifier] then
                return nil, "identidade openid vazia ou duplicada"
            end
            identifiers[username] = identifier
            identity_owners[identifier] = username
        end
    end
    return identifiers
end

local function identifiers_by_username()
    local document, err = read_document()
    if not document then return nil, err end
    return index_document(document)
end

function M.list_identifiers_by_username()
    return identifiers_by_username()
end

function M.find_identifier(username)
    local clean_username = trim(username)
    if clean_username == "" then
        return nil, "username ausente"
    end

    local identifiers, err = identifiers_by_username()
    if not identifiers then
        return nil, err
    end

    return identifiers[clean_username], nil
end

-- One fresh identity document and one lock per snapshot, never a cross-request cache.
function M.ensure_identifiers(usernames)
    if type(usernames) ~= "table" then return nil, nil, "lista de usernames invalida" end
    local count = 0
    for index in pairs(usernames) do
        count = count + 1
        if type(index) ~= "number" or index % 1 ~= 0 or index < 1 or index > #usernames then
            return nil, nil, "lista de usernames invalida"
        end
    end
    if count ~= #usernames then return nil, nil, "lista de usernames invalida" end
    local requested = {}
    local seen = {}
    for _, username in ipairs(usernames) do
        if type(username) ~= "string" or trim(username) == "" then
            return nil, nil, "username ausente ou invalido"
        end
        local clean = trim(username)
        if seen[clean] then return nil, nil, "username duplicado" end
        seen[clean] = true
        requested[#requested + 1] = clean
    end
    local result, lock_err = file_store.with_lock(IDS_LOCK, function()
        local identifiers, read_err = identifiers_by_username()
        if not identifiers then return { error = read_err } end
        local created = {}
        for _, username in ipairs(requested) do
            created[username] = false
            if not identifiers[username] then
                -- Canonical provisioning of a new identity, not a substituted ID.
                local generated, generate_err = generate_identifier(username)
                if not generated then return { error = generate_err } end
                identifiers, read_err = identifiers_by_username()
                if not identifiers then return { error = read_err } end
                if not identifiers[username] then
                    return { error = "opaque identifier nao encontrado apos generate/export" }
                end
                created[username] = true
            end
        end
        return { identifiers = identifiers, created = created }
    end)
    if not result then return nil, nil, lock_err end
    if result.error then return nil, nil, result.error end
    return result.identifiers, result.created, nil
end

function M.ensure_identifier(username)
    if type(username) ~= "string" or trim(username) == "" then return nil, false, "username ausente ou invalido" end
    local identifiers, created, err = M.ensure_identifiers({ username })
    if not identifiers then return nil, false, err end
    local clean = trim(username)
    if not identifiers[clean] then return nil, false, "username ausente" end
    return identifiers[clean], created[clean], nil
end

function M.remove_identifier(username)
    local clean_username = trim(username)
    if clean_username == "" then
        return nil, "username ausente"
    end

    local result, lock_err = file_store.with_lock(IDS_LOCK, function()
        local document, read_err = read_document()
        if not document then
            return nil, read_err
        end

        local filtered = {}
        local removed = false
        for _, entry in ipairs(document.identifiers) do
            local entry_username = trim(entry.username)
            if entry.service == OPENID_SERVICE
                and entry_username == clean_username
            then
                removed = true
            else
                table.insert(filtered, entry)
            end
        end

        if not removed then
            return true
        end

        document.identifiers = filtered
        return write_document(document)
    end)

    if result == nil then
        return nil, lock_err
    end
    return result, lock_err
end

return M
