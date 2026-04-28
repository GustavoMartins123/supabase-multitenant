local lyaml = require "lyaml"
local shell = require "resty.shell"

local IDS_PATH = "/config/ids.yml"
local CONFIG_PATH = "/config/configuration.yml"
local AUTHELIA_BIN = "/usr/local/bin/authelia"
local OPENID_SERVICE = "openid"
local COMMAND_TIMEOUT_MS = 10000

local M = {}

local function trim(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function read_document()
    local handle, err = io.open(IDS_PATH, "r")
    if not handle then
        return { identifiers = {} }, nil
    end

    local content = handle:read("*a") or ""
    handle:close()

    if content:gsub("%s+", "") == "" then
        return { identifiers = {} }, nil
    end

    local document = lyaml.load(content)
    if type(document) ~= "table" then
        return nil, "ids.yml invalido"
    end

    if type(document.identifiers) ~= "table" then
        document.identifiers = {}
    end

    return document, nil
end

local function write_document(document)
    local serialized = lyaml.dump({ document })
    local handle, err = io.open(IDS_PATH, "w")
    if not handle then
        return nil, err
    end

    handle:write(serialized)
    handle:close()
    return true
end

local function is_safe_username(username)
    return username:match("^[%w._@%-]+$") ~= nil
end

local function run_authelia_command(args)
    local ok, stdout, stderr, reason, status = shell.run(args, nil, COMMAND_TIMEOUT_MS, 65536)
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
    local tmp_path = string.format("%s.tmp.%s.%s", IDS_PATH, tostring(ngx.worker.pid()), tostring(math.random(10000, 99999)))
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

function M.list_identifiers_by_username()
    local document, err = read_document()
    if not document then
        return nil, err
    end

    local identifiers = {}
    for _, entry in ipairs(document.identifiers or {}) do
        local username = trim(entry.username)
        local identifier = trim(entry.identifier)
        if entry.service == OPENID_SERVICE and username ~= "" and identifier ~= "" then
            identifiers[username] = identifier
        end
    end

    return identifiers, nil
end

function M.find_identifier(username)
    local clean_username = trim(username)
    if clean_username == "" then
        return nil, "username ausente"
    end

    local identifiers, err = M.list_identifiers_by_username()
    if not identifiers then
        return nil, err
    end

    return identifiers[clean_username], nil
end

function M.ensure_identifier(username)
    local clean_username = trim(username)
    if clean_username == "" then
        return nil, false, "username ausente"
    end

    local document, err = read_document()
    if not document then
        return nil, false, err
    end

    for _, entry in ipairs(document.identifiers or {}) do
        local entry_username = trim(entry.username)
        local entry_identifier = trim(entry.identifier)
        if entry.service == OPENID_SERVICE and entry_username == clean_username and entry_identifier ~= "" then
            return entry_identifier, false, nil
        end
    end

    local ok, generate_err = generate_identifier(clean_username)
    if not ok then
        return nil, false, generate_err
    end

    local identifier, find_err = M.find_identifier(clean_username)
    if not identifier or identifier == "" then
        return nil, true, find_err or "opaque identifier nao encontrado apos generate/export"
    end

    return identifier, true, nil
end

function M.remove_identifier(username)
    local clean_username = trim(username)
    if clean_username == "" then
        return nil, "username ausente"
    end

    local document, err = read_document()
    if not document then
        return nil, err
    end

    local filtered = {}
    local removed = false

    for _, entry in ipairs(document.identifiers or {}) do
        local entry_username = trim(entry.username)
        if entry.service == OPENID_SERVICE and entry_username == clean_username then
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
end

return M
