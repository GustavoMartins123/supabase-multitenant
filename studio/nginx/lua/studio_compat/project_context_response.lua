local cjson = require("cjson")
local project_access = require("security.project_access")

local context = ngx.ctx.studio_project_context or project_access.enforce()
if type(context) ~= "table" then
    return
end

local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local protocol, authority = server_domain:match("^(https?)://([^/]+)")
protocol = protocol or "https"
authority = authority or server_domain:gsub("^https?://", "")
local db_host = authority:match("^([^:]+)") or authority
local ref = context.ref
local display_name = context.display_name or ref
local tenant_endpoint = authority .. "/" .. ref
local rest_url = server_domain .. "/" .. ref .. "/rest/v1/"
local inserted_at = "2021-08-02T06:40:40.646Z"

local function array(items)
    return setmetatable(items or {}, cjson.array_mt)
end

local anon_key = {
    api_key = context.anon_key,
    name = "anon key",
    tags = "anon",
}

local function project_detail()
    return {
        id = 1,
        project_uuid = context.project_uuid,
        tenant_uuid = context.tenant_uuid,
        ref = ref,
        name = display_name,
        organization_id = 1,
        cloud_provider = "localhost",
        status = "ACTIVE_HEALTHY",
        region = "local",
        inserted_at = inserted_at,
        connectionString = "",
        restUrl = rest_url,
    }
end

local function project_summary()
    local summary = project_detail()
    summary.services = array({})
    return summary
end

local function projects_response()
    local version = ngx.req.get_headers()["Version"]
        or ngx.req.get_headers()["version"]
    if tostring(version or "") ~= "2" then
        return array({ project_detail() })
    end

    return {
        projects = array({ project_summary() }),
        pagination = {
            count = 1,
            limit = tonumber(ngx.var.arg_limit) or 100,
            offset = tonumber(ngx.var.arg_offset) or 0,
        },
    }
end

local function project_settings()
    return {
        app_config = {
            db_schema = "public",
            endpoint = tenant_endpoint,
            storage_endpoint = tenant_endpoint,
            protocol = protocol,
        },
        cloud_provider = "AWS",
        db_dns_name = "-",
        db_host = db_host,
        db_ip_addr_config = "legacy",
        db_name = "postgres",
        db_port = 5432,
        db_user = "postgres",
        inserted_at = inserted_at,
        jwt_secret = "",
        name = display_name,
        project_uuid = context.project_uuid,
        tenant_uuid = context.tenant_uuid,
        ref = ref,
        region = "local",
        service_api_keys = array({ anon_key }),
        ssl_enforced = false,
        status = "ACTIVE_HEALTHY",
        file_size_limit = tonumber(context.file_size_limit),
    }
end

local function project_props()
    local app_config = {
        db_schema = "public",
        endpoint = tenant_endpoint,
        realtime_enabled = true,
    }
    local encrypted_anon = {
        api_key_encrypted = "-",
        name = "anon key",
        tags = "anon",
    }
    return {
        project = {
            id = 1,
            ref = ref,
            name = display_name,
            organization_id = 1,
            cloud_provider = "localhost",
            status = "ACTIVE_HEALTHY",
            region = "local",
            inserted_at = inserted_at,
            api_key_supabase_encrypted = "",
            db_host = db_host,
            db_name = "postgres",
            db_port = 5432,
            db_ssl = false,
            db_user = "postgres",
            services = array({
                {
                    id = 1,
                    name = "Default API",
                    app = { id = 1, name = "Auto API" },
                    app_config = app_config,
                    service_api_keys = array({ encrypted_anon }),
                },
            }),
        },
        autoApiService = {
            id = 1,
            name = "Default API",
            project = { ref = ref },
            app = { id = 1, name = "Auto API" },
            app_config = app_config,
            protocol = protocol,
            endpoint = tenant_endpoint,
            restUrl = rest_url,
            defaultApiKey = context.anon_key,
            serviceApiKey = "",
            service_api_keys = array({ encrypted_anon }),
        },
    }
end

local function databases()
    return array({
        {
            cloud_provider = "localhost",
            connectionString = "",
            connection_string_read_only = "",
            db_host = db_host,
            db_name = "postgres",
            db_port = 5432,
            db_user = "postgres",
            identifier = ref,
            inserted_at = "",
            region = "local",
            restUrl = rest_url,
            size = "",
            status = "ACTIVE_HEALTHY",
        },
    })
end

local function api_keys()
    return array({
        {
            name = "anon",
            api_key = context.anon_key,
            id = "anon",
            type = "legacy",
            hash = "",
            prefix = "",
            description = "Legacy anon API key",
        },
    })
end

local function project_config()
    return {
        db_anon_role = "anon",
        db_extra_search_path = "public",
        db_schema = "public,storage,graphql_public",
        jwt_secret = "",
        max_rows = 1000,
        role_claim_key = ".role",
    }
end

local function profile()
    local email = ngx.var.authelia_email or ""
    local username = email:match("^([^@]+)") or email
    return {
        id = 1,
        primary_email = email,
        username = username,
        first_name = "",
        last_name = "",
        organizations = array({
            {
                id = 1,
                name = os.getenv("DEFAULT_ORGANIZATION_NAME") or "Default Organization",
                slug = "default-org-slug",
                billing_email = email,
                projects = array({ project_detail() }),
            },
        }),
    }
end

local function anon_api_key()
    return {
        name = "anon",
        api_key = context.anon_key,
        id = "anon",
        type = "legacy",
        hash = "",
        prefix = "",
        description = "Legacy anon API key",
    }
end

local uri = ngx.var.uri or ""
local payload
if uri:match("/api%-keys/temporary/?$") then
    if ngx.req.get_method() ~= "POST" then
        ngx.header["Allow"] = "POST"
        return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
    end
    payload = { api_key = context.anon_key }
elseif ngx.req.get_method() ~= "GET" then
    ngx.header["Allow"] = "GET"
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
elseif uri:match("^/api/v1/projects/[^/]+/api%-keys/?$") then
    payload = api_keys()
elseif uri:match("^/api/v1/projects/[^/]+/api%-keys/anon/?$") then
    payload = anon_api_key()
elseif uri:match("^/api/v1/projects/[^/]+/api%-keys/") then
    ngx.status = ngx.HTTP_NOT_FOUND
    ngx.header["Content-Type"] = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    ngx.say(cjson.encode({ error = { message = "API key not found" } }))
    return ngx.exit(ngx.HTTP_NOT_FOUND)
elseif uri == "/api/platform/profile" then
    payload = profile()
elseif uri == "/api/platform/projects" or uri == "/api/platform/projects/" then
    payload = projects_response()
elseif uri:match("^/api/platform/props/project/[^/]+/?$") then
    payload = { project = project_summary() }
elseif uri:match("^/api/platform/projects/[^/]+/config/?$")
    or uri:match("^/api/platform/projects/[^/]+/config/postgrest/?$")
then
    payload = project_config()
elseif uri:match("^/api/platform/props/project/[^/]+/api/?$") then
    payload = project_props()
elseif uri:match("/databases/?$") then
    payload = databases()
elseif uri:match("/settings/?$") then
    payload = project_settings()
else
    payload = project_detail()
end

ngx.status = ngx.HTTP_OK
ngx.header["Content-Type"] = "application/json; charset=utf-8"
ngx.header["Cache-Control"] = "no-store"
ngx.say(cjson.encode(payload))
return ngx.exit(ngx.HTTP_OK)
