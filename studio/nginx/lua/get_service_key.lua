-- get_service_key.lua
-- Módulo para recuperar chaves de serviço de forma segura

local http = require "resty.http"
local fernet = require "resty.fernet"
local cjson = require "cjson"

-- Configurações
local SERVER_IP= os.getenv("SERVER_IP")
local DSN = "http://" .. SERVER_IP
local TOKEN = os.getenv("NGINX_SHARED_TOKEN")
local SEC = os.getenv("FERNET_SECRET")
local cache = ngx.shared.service_keys

-- Função principal
local function get_service_key(ref)
    -- Verificar se o ref é válido
    if not ref or ref == "" or ref == "default" then
        ngx.log(ngx.WARN, "Ref inválido ou default")
        return ""
    end
    
    -- Verificar cache primeiro
    local k = cache:get(ref)
    if k then 
        ngx.log(ngx.DEBUG, "Cache hit para ref: ", ref)
        return k 
    end
    
    ngx.log(ngx.DEBUG, "Cache miss para ref: ", ref, ", buscando do serviço")
    
    -- Verificar se o token e secret estão definidos
    if not TOKEN or TOKEN == "" then
        ngx.log(ngx.ERR, "NGINX_SHARED_TOKEN não definido")
        return ""
    end
    
    if not SEC or SEC == "" then
        ngx.log(ngx.ERR, "FERNET_SECRET não definido")
        return ""
    end
    
    -- Inicializar cliente HTTP
    local httpc = http.new()
    httpc:set_timeout(1000)
    
    -- Fazer requisição HTTP
    local res, err = httpc:request_uri(
        DSN .. "/api/projects/internal/enc-key/" .. ref,
        { 
            headers = {["X-Shared-Token"] = TOKEN}, 
            method = "GET",
            keepalive = true 
        }
    )
    
    -- Tratar erros de conexão
    if not res then
        ngx.log(ngx.ERR, "Falha na requisição de enc-key: ", err)
        return ""
    end
    
    -- Verificar status da resposta
    if res.status ~= 200 then
        ngx.log(ngx.ERR, "Falha na busca de enc-key, status: ", res.status)
        return ""
    end
    
    -- Analisar resposta JSON
    local ok, data = pcall(cjson.decode, res.body)
    if not ok or not data.enc_service_key then
        ngx.log(ngx.ERR, "Falha ao analisar resposta enc-key: ", res.body)
        return ""
    end
    
    -- Descriptografar a chave
    local f = fernet:new(SEC)
    local ok, plain = pcall(f.decrypt, f, data.enc_service_key)
    if not ok then
        ngx.log(ngx.ERR, "Falha na descriptografia fernet: ", plain)
        return ""
    end
    
    -- Armazenar em cache
    cache:set(ref, plain, 600) -- TTL 10 min
    
    return plain
end

return get_service_key