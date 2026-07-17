local cjson = require("cjson.safe")
local fernet = require("resty.fernet")
local http = require("resty.http")

local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local hostname = string.match(server_domain or "", "//([^/:]+)") or "localhost"
local shared_token = os.getenv("NGINX_SHARED_TOKEN")
local encryption_key = os.getenv("STUDIO_SERVICE_KEY_ENCRYPTION_KEY")
local cache_ttl = tonumber(os.getenv("SERVICE_KEY_CACHE_TTL_SECONDS")) or 60
local version_check_ttl = tonumber(os.getenv("SERVICE_KEY_VERSION_CHECK_TTL_SECONDS")) or 5
local verify_tls_value = (os.getenv("SERVICE_KEY_VERIFY_TLS") or "true"):lower()
local verify_tls = verify_tls_value ~= "0"
    and verify_tls_value ~= "false"
    and verify_tls_value ~= "no"
    and verify_tls_value ~= "off"
local cache = ngx.shared.service_keys
local metrics = ngx.shared.service_key_metrics

cache_ttl = math.max(1, math.min(cache_ttl, 3600))
version_check_ttl = math.max(1, math.min(version_check_ttl, cache_ttl))

local function increment_metric(name)
    local _, err = metrics:incr(name, 1, 0)
    if err then
        ngx.log(ngx.WARN, "Falha ao incrementar métrica de service key: ", err)
    end
end

local function cache_key(project_ref)
    return "service_key:value:" .. project_ref
end

local function cached_version_key(project_ref)
    return "service_key:cached_version:" .. project_ref
end

local function required_version_key(project_ref)
    return "service_key:required_version:" .. project_ref
end

local function checked_version_key(project_ref)
    return "service_key:checked_version:" .. project_ref
end

local function internal_request(path)
    local http_client = http.new()
    http_client:set_timeout(1000)
    return http_client:request_uri(server_domain .. path, {
        headers = {
            ["X-Shared-Token"] = shared_token,
            ["X-Internal-Service"] = "studio-nginx",
            ["Host"] = hostname,
        },
        ssl_verify = verify_tls,
        ssl_server_name = hostname,
        method = "GET",
        keepalive = true,
    })
end

local function refresh_required_version(project_ref)
    local response, err = internal_request(
        "/api/projects/internal/key-version/" .. project_ref
    )
    if not response or response.status ~= ngx.HTTP_OK then
        increment_metric("version_check_error")
        ngx.log(
            ngx.WARN,
            "Falha ao consultar versão da service key: ",
            err or (response and response.status) or "sem resposta"
        )
        local fallback_version = cache:get(required_version_key(project_ref))
            or cache:get(cached_version_key(project_ref))
            or 0
        -- Evita uma chamada bloqueante por request durante indisponibilidade.
        cache:set(checked_version_key(project_ref), fallback_version, version_check_ttl)
        return fallback_version
    end

    local data = cjson.decode(response.body)
    local version = data and tonumber(data.project_key_version)
    if not version then
        increment_metric("version_check_error")
        local fallback_version = cache:get(required_version_key(project_ref))
            or cache:get(cached_version_key(project_ref))
            or 0
        cache:set(checked_version_key(project_ref), fallback_version, version_check_ttl)
        return fallback_version
    end
    cache:set(required_version_key(project_ref), version)
    cache:set(checked_version_key(project_ref), version, version_check_ttl)
    return version
end

local function get_required_version(project_ref)
    local checked_version = cache:get(checked_version_key(project_ref))
    if checked_version then
        return checked_version
    end
    return refresh_required_version(project_ref)
end

local function fetch_service_key(project_ref)
    local response, err = internal_request(
        "/api/projects/internal/enc-key/" .. project_ref
    )
    if not response then
        ngx.log(ngx.ERR, "Falha na requisição de enc-key: ", err)
        return nil
    end
    if response.status ~= ngx.HTTP_OK then
        ngx.log(ngx.ERR, "Falha na busca de enc-key, status: ", response.status)
        return nil
    end

    local data = cjson.decode(response.body)
    if not data or not data.enc_service_key or not data.project_key_version then
        ngx.log(ngx.ERR, "Resposta enc-key inválida")
        return nil
    end

    local cipher = fernet:new(encryption_key)
    local ok, plaintext = pcall(cipher.decrypt, cipher, data.enc_service_key)
    if not ok then
        ngx.log(ngx.ERR, "Falha na descriptografia da service key")
        return nil
    end
    return plaintext, tonumber(data.project_key_version)
end

local function get_service_key(project_ref)
    if not project_ref or project_ref == "" or project_ref == "default" then
        return ""
    end
    if server_domain == ""
        or not shared_token or shared_token == ""
        or not encryption_key or encryption_key == ""
    then
        ngx.log(ngx.ERR, "Configuração do cache de service key ausente")
        return ""
    end

    local required_version = get_required_version(project_ref)
    local value = cache:get(cache_key(project_ref))
    local cached_version = cache:get(cached_version_key(project_ref)) or 0
    if value and cached_version >= required_version then
        increment_metric("hit")
        return value
    end

    increment_metric("miss")
    if value then
        increment_metric("version_reload")
        cache:delete(cache_key(project_ref))
        cache:delete(cached_version_key(project_ref))
    end

    local plaintext, fetched_version = fetch_service_key(project_ref)
    if not plaintext or not fetched_version then
        increment_metric("fetch_error")
        return ""
    end

    cache:set(cache_key(project_ref), plaintext, cache_ttl)
    cache:set(cached_version_key(project_ref), fetched_version, cache_ttl)
    cache:set(required_version_key(project_ref), fetched_version)
    cache:set(checked_version_key(project_ref), fetched_version, version_check_ttl)
    return plaintext
end

return get_service_key
