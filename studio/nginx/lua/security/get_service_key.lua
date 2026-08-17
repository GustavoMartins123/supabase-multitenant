local cjson = require("cjson.safe")
local fernet = require("resty.fernet")
local http = require("resty.http")
local internal_hmac = require("security.internal_hmac")
local service_key_version = require("cache.service_key_version")
local outbound_tls = require("utils.outbound_tls")

local server_domain = (os.getenv("SERVER_DOMAIN") or ""):gsub("/+$", "")
local hostname = string.match(server_domain or "", "//([^/:]+)") or "localhost"
local hmac_secret = os.getenv("STUDIO_GATEWAY_HMAC_SECRET")
local encryption_key = os.getenv("STUDIO_SERVICE_KEY_ENCRYPTION_KEY")
local cache_ttl = tonumber(os.getenv("SERVICE_KEY_CACHE_TTL_SECONDS")) or 60
local fetch_error_ttl = tonumber(os.getenv("SERVICE_KEY_FETCH_ERROR_TTL_SECONDS")) or 2
local cache = ngx.shared.service_keys
local metrics = ngx.shared.service_key_metrics

cache_ttl = math.max(1, math.min(cache_ttl, 3600))
fetch_error_ttl = math.max(1, math.min(fetch_error_ttl, 10))

local function increment_metric(name)
    local _, err = metrics:incr(name, 1, 0)
    if err then
        ngx.log(ngx.WARN, "Falha ao incrementar métrica de service key: ", err)
    end
end

local function fetch_error_key(project_ref)
    return "service_key:fetch_error:" .. project_ref
end

local function internal_request(path)
    local signed_headers, sign_err = internal_hmac.sign_headers(
        hmac_secret,
        "studio-gateway",
        "GET",
        path,
        ""
    )
    if not signed_headers then
        return nil, sign_err or "falha ao assinar chamada interna"
    end
    signed_headers["Host"] = hostname

    local http_client = http.new()
    http_client:set_timeout(1000)
    local url = server_domain .. path
    return http_client:request_uri(url, outbound_tls.apply_internal(url, {
        headers = signed_headers,
        method = "GET",
        keepalive = true,
    }))
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
        return nil, "version_check_failed"
    end

    local data = cjson.decode(response.body)
    local version = data and tonumber(data.project_key_version)
    if not version then
        increment_metric("version_check_error")
        return nil, "invalid_version_response"
    end
    local required, promote_err = service_key_version.promote(project_ref, version)
    if not required then
        increment_metric("version_check_error")
        ngx.log(ngx.ERR, "Falha ao promover versao da service key: ", promote_err)
        return nil, promote_err or "version_promote_failed"
    end
    return required
end

local function get_required_version(project_ref)
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

    local constructor_ok, cipher = pcall(fernet.new, fernet, encryption_key)
    if not constructor_ok or not cipher then
        ngx.log(ngx.ERR, "Chave de transporte Fernet invalida")
        return nil
    end
    local decrypt_ok, plaintext = pcall(cipher.decrypt, cipher, data.enc_service_key)
    if not decrypt_ok or not plaintext then
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
        or not hmac_secret or hmac_secret == ""
        or not encryption_key or encryption_key == ""
    then
        ngx.log(ngx.ERR, "Configuração do cache de service key ausente")
        return ""
    end

    local required_version, version_err = get_required_version(project_ref)
    if not required_version then
        increment_metric("fetch_error")
        ngx.log(
            ngx.ERR,
            "Service key bloqueada por falha na verificacao de versao: ",
            version_err or "unknown"
        )
        return ""
    end
    local value, cache_state = service_key_version.read_cached(project_ref)
    if cache_state == "hit" then
        increment_metric("hit")
        return value
    end
    if cache_state ~= "miss" and cache_state ~= "stale" then
        increment_metric("fetch_error")
        ngx.log(ngx.ERR, "Falha ao ler cache de service key: ", cache_state)
        return ""
    end

    increment_metric("miss")
    if cache:get(fetch_error_key(project_ref)) then
        increment_metric("fetch_error_backoff")
        return ""
    end
    if cache_state == "stale" then
        increment_metric("version_reload")
    end

    local plaintext, fetched_version = fetch_service_key(project_ref)
    if not plaintext or not fetched_version then
        increment_metric("fetch_error")
        cache:set(fetch_error_key(project_ref), true, fetch_error_ttl)
        return ""
    end

    local published, required_or_err = service_key_version.publish(
        project_ref,
        plaintext,
        fetched_version,
        cache_ttl
    )
    if not published then
        if type(required_or_err) == "number" then
            increment_metric("stale_fetch")
            ngx.log(
                ngx.WARN,
                "Resposta enc-key obsoleta para ",
                project_ref,
                ": recebida=",
                fetched_version,
                " requerida=",
                required_or_err
            )
        else
            increment_metric("fetch_error")
            ngx.log(ngx.ERR, "Falha ao publicar service key no cache: ", required_or_err)
        end
        cache:set(fetch_error_key(project_ref), true, fetch_error_ttl)
        return ""
    end
    return plaintext
end

return get_service_key
