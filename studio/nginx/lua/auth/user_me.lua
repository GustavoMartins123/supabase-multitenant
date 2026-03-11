local groups = ngx.var.authelia_groups or ""
local groups_clean = groups:gsub("[%[%]]", "")
local is_admin = false

for group in groups_clean:gmatch("[^,]+") do
    if group:match("^%s*admin%s*$") then
        is_admin = true
        break
    end
end

if ngx.var.request_method ~= "GET" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local email = ngx.var.authelia_email
if email and email ~= "" then
    local resty_sha2 = require "resty.sha256"
    local str = require "resty.string"
    
    local normalized_email = email:lower():gsub("%s+", "")
    
    local hasher = resty_sha2:new()
    hasher:update(normalized_email)
    local digest = hasher:final()
    local hash = str.to_hex(digest)
    
    local cache = ngx.shared.users_cache
    local user_data_json = cache:get(hash)
    
    if user_data_json then
        local cjson = require "cjson.safe"
        local user_data = cjson.decode(user_data_json)
        
        if user_data then
            ngx.var.username = user_data.username or ""
            ngx.var.display_name = user_data.display_name or ""
            ngx.var.user_hash = hash
            
            ngx.log(ngx.INFO, "[USER_ME] Usuário encontrado no cache: " .. 
                (user_data.username or "N/A") .. " (" .. normalized_email .. ")")
        else
            ngx.log(ngx.WARN, "[USER_ME] Erro ao decodificar dados do usuário do cache")
        end
    else
        ngx.log(ngx.WARN, "[USER_ME] Usuário não encontrado no cache para email: " .. 
            normalized_email .. " (hash: " .. hash .. ")")
    end
else
    ngx.log(ngx.WARN, "[USER_ME] Email não fornecido pelo Authelia")
end

ngx.var.myrole = is_admin and "true" or "false"
