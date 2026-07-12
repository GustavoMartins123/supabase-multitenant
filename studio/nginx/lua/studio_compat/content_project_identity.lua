local cjson = require("cjson.safe")
local http = require("resty.http")

local M = {}

local SERVER_DOMAIN = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local SERVER_HOSTNAME = string.match(SERVER_DOMAIN, "//([^/:]+)") or "localhost"
local SHARED_TOKEN = os.getenv("NGINX_SHARED_TOKEN") or ""
local CACHE_TTL_SECONDS = 30
local cache = ngx.shared.service_keys

local function valid_project_ref(value)
    return type(value) == "string"
        and ngx.re.match(value, [[^[a-z_][a-z0-9_]{2,39}$]], "jo") ~= nil
end

local function valid_uuid(value)
    return type(value) == "string"
        and ngx.re.match(
            value,
            [[^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$]],
            "jo"
        ) ~= nil
end

local function cache_key(project_ref)
    return "content:project-identity:" .. project_ref
end

local function normalize_identity(payload, requested_ref)
    if type(payload) ~= "table" then
        return nil, "invalid identity payload"
    end

    local project_id = tostring(payload.project_id or ""):lower()
    if not valid_uuid(project_id) then
        return nil, "invalid stable project id"
    end

    local current_ref = payload.current_ref
    if not valid_project_ref(current_ref) then
        current_ref = requested_ref
    end

    local aliases = {}
    local seen = {}
    local function append(value)
        if valid_project_ref(value) and not seen[value] then
            seen[value] = true
            table.insert(aliases, value)
        end
    end

    append(current_ref)
    append(requested_ref)
    for _, value in ipairs(payload.aliases or {}) do
        append(value)
    end

    return {
        project_id = project_id,
        current_ref = current_ref,
        aliases = aliases,
    }
end

local function fetch_identity(project_ref)
    if SERVER_DOMAIN == "" or SHARED_TOKEN == "" then
        return nil, "content identity configuration is missing"
    end

    local client = http.new()
    client:set_timeout(2000)
    local response, err = client:request_uri(
        SERVER_DOMAIN
            .. "/api/projects/internal/content-identity/"
            .. ngx.escape_uri(project_ref),
        {
            method = "GET",
            headers = {
                ["Accept"] = "application/json",
                ["Host"] = SERVER_HOSTNAME,
                ["X-Shared-Token"] = SHARED_TOKEN,
                ["X-Internal-Service"] = "studio-nginx",
            },
            ssl_verify = false,
            keepalive = true,
        }
    )

    if not response then
        return nil, "content identity request failed: " .. (err or "unknown error")
    end
    if response.status ~= ngx.HTTP_OK then
        return nil, "content identity returned HTTP " .. tostring(response.status)
    end

    local decoded, decode_err = cjson.decode(response.body or "")
    if not decoded then
        return nil, "content identity JSON is invalid: " .. (decode_err or "decode failed")
    end
    return normalize_identity(decoded, project_ref)
end

function M.resolve(project_ref)
    if not valid_project_ref(project_ref) then
        return nil, "invalid selected project ref"
    end

    if cache then
        local cached = cache:get(cache_key(project_ref))
        if cached then
            local decoded = cjson.decode(cached)
            local identity = decoded and normalize_identity(decoded, project_ref)
            if identity then
                return identity
            end
            cache:delete(cache_key(project_ref))
        end
    end

    local identity, err = fetch_identity(project_ref)
    if not identity then
        return nil, err
    end

    if cache then
        local encoded = cjson.encode(identity)
        if encoded then
            cache:set(cache_key(project_ref), encoded, CACHE_TTL_SECONDS)
        end
    end

    return identity
end

return M
