local bit = require("bit")
local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local http = require("resty.http")
local user_identity = require("project_context.user_identity")
local content_project_identity = require("studio_compat.content_project_identity")

local _M = {}

local function json_array(items)
    local arr = items or {}
    return setmetatable(arr, cjson.array_mt)
end

local function simple_hash(input)
    local hash = 0
    for i = 1, #input do
        local code = input:byte(i)
        hash = bit.tobit(bit.lshift(hash, 5) - hash + code)
    end

    if hash == -2147483648 then
        return 2147483648
    end

    if hash < 0 then
        return -hash
    end

    return hash
end

local function deterministic_uuid(inputs)
    local cleaned = {}
    for _, value in ipairs(inputs or {}) do
        if value and value ~= "" then
            table.insert(cleaned, tostring(value))
        end
    end

    local seed = simple_hash(table.concat(cleaned, "_"))
    local bytes = {}

    for i = 1, 16 do
        -- Intentionally use Lua number arithmetic here so the LCG matches
        -- the Studio's JavaScript implementation, including floating-point
        -- precision loss before the 32-bit bitwise mask.
        seed = bit.band(seed * 1103515245 + 12345, 0x7fffffff)
        bytes[i] = bit.band(bit.rshift(seed, 16), 0xff)
    end

    bytes[7] = bit.bor(bit.band(bytes[7], 0x0f), 0x40)
    bytes[9] = bit.bor(bit.band(bytes[9], 0x3f), 0x80)

    local parts = {}
    for i = 1, 16 do
        parts[i] = string.format("%02x", bytes[i])
    end

    return table.concat({
        table.concat(parts, "", 1, 4),
        table.concat(parts, "", 5, 6),
        table.concat(parts, "", 7, 8),
        table.concat(parts, "", 9, 10),
        table.concat(parts, "", 11, 16),
    }, "-")
end

local STUDIO_BASE_URL = "http://studio:3000"
local respond_json

local function get_user_id()
    local email = user_identity.normalize_email(ngx.var.authelia_email or "")
    if email == "" then
        return nil, "authelia_email unavailable"
    end

    local cache = ngx.shared.users_cache
    local user_id = cache and cache:get("email:" .. email)
    if user_id and user_id ~= "" then
        return user_id
    end

    return nil, "user uuid unavailable"
end

local function get_project_ref()
    return ngx.var.uri:match("^/api/platform/projects/([^/]+)/content")
end

local function get_selected_project_ref()
    local api_ref = get_project_ref()
    local context = ngx.ctx.studio_project_context
    if type(context) == "table" and context.ref == api_ref then
        return context.ref
    end
    return nil
end

local function require_project_scope()
    local selected_ref = get_selected_project_ref()
    if not selected_ref then
        return respond_json(403, {
            error = {
                message = "Selecione um projeto antes de acessar snippets.",
            },
        })
    end

    local identity, identity_err = content_project_identity.resolve(selected_ref)
    if identity then
        return identity.project_id
    end

    ngx.log(
        ngx.ERR,
        "[CONTENT-PROXY] Failed to resolve stable project identity for ",
        selected_ref,
        ": ",
        identity_err or "unknown error"
    )
    return respond_json(502, {
        error = {
            message = "Failed to resolve stable project identity",
        },
    })
end

local function read_body()
    ngx.req.read_body()

    local body = ngx.req.get_body_data()
    if body then
        return body
    end

    local body_file = ngx.req.get_body_file()
    if not body_file then
        return nil
    end

    local file, err = io.open(body_file, "rb")
    if not file then
        return nil, err
    end

    local data = file:read("*a")
    file:close()
    return data
end

local function request_headers(extra_headers)
    local incoming = ngx.req.get_headers()
    local headers = {
        ["Accept"] = incoming["accept"] or "application/json",
        ["Authorization"] = incoming["authorization"],
        ["Content-Type"] = incoming["content-type"],
        ["Cookie"] = incoming["cookie"],
        ["X-Forwarded-For"] = incoming["x-forwarded-for"] or ngx.var.remote_addr,
        ["X-Forwarded-Host"] = ngx.var.host,
        ["X-Forwarded-Proto"] = ngx.var.scheme,
        ["X-Real-IP"] = ngx.var.remote_addr,
    }

    if extra_headers then
        for key, value in pairs(extra_headers) do
            headers[key] = value
        end
    end

    for key, value in pairs(headers) do
        if value == nil or value == "" then
            headers[key] = nil
        end
    end

    return headers
end

local function studio_request(method, path, opts)
    opts = opts or {}

    local httpc = http.new()
    httpc:set_timeout(10000)

    local request_path = path
    if opts.query and next(opts.query) ~= nil then
        request_path = request_path .. "?" .. ngx.encode_args(opts.query)
    end

    return httpc:request_uri(STUDIO_BASE_URL .. request_path, {
        method = method,
        body = opts.body,
        headers = request_headers(opts.headers),
        keepalive = false,
    })
end

function respond_json(status, payload)
    ngx.status = status
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.say(cjson.encode(payload))
    return ngx.exit(status)
end

local function respond_from_studio(res)
    ngx.status = res.status

    local content_type = res.headers["Content-Type"] or res.headers["content-type"]
    if content_type then
        ngx.header["Content-Type"] = content_type
    else
        ngx.header["Content-Type"] = "application/json; charset=utf-8"
    end

    local cache_control = res.headers["Cache-Control"] or res.headers["cache-control"]
    if cache_control then
        ngx.header["Cache-Control"] = cache_control
    end

    local set_cookie = res.headers["Set-Cookie"] or res.headers["set-cookie"]
    if set_cookie then
        ngx.header["Set-Cookie"] = set_cookie
    end

    if res.body and res.body ~= "" then
        ngx.print(res.body)
    end
    return ngx.exit(res.status)
end

local function passthrough_current_request(path_override, query_override, body_override)
    local path = path_override or ngx.var.uri
    local query = query_override or ngx.req.get_uri_args()
    local body = body_override
    if body == nil and ngx.req.get_method() ~= "GET" and ngx.req.get_method() ~= "HEAD" then
        body = read_body()
    end

    local res, err = studio_request(ngx.req.get_method(), path, {
        query = query,
        body = body,
    })

    if not res then
        ngx.log(ngx.ERR, "[CONTENT-PROXY] Studio passthrough failed: ", err or "unknown error")
        return respond_json(502, { error = { message = "Studio proxy request failed" } })
    end

    return respond_from_studio(res)
end

local function parse_json_response(res)
    if not res.body or res.body == "" then
        return {}
    end

    return cjson_safe.decode(res.body) or {}
end

_M.get_user_id = get_user_id
_M.get_project_ref = get_project_ref
_M.get_selected_project_ref = get_selected_project_ref
_M.require_project_scope = require_project_scope
_M.read_body = read_body
_M.request_headers = request_headers
_M.studio_request = studio_request
_M.respond_json = respond_json
_M.respond_from_studio = respond_from_studio
_M.passthrough_current_request = passthrough_current_request
_M.parse_json_response = parse_json_response
_M.json_array = json_array
_M.simple_hash = simple_hash
_M.deterministic_uuid = deterministic_uuid
_M.STUDIO_BASE_URL = STUDIO_BASE_URL

return _M
