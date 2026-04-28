local groups = ngx.var.authelia_groups or ""
local groups_clean = groups:gsub("[%[%]]", "")
local is_admin = false
local user_identity = require "user_identity"
local user_context_headers = require "user_context_headers"

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
    local normalized_email = user_identity.normalize_email(email)
    local cache = ngx.shared.users_cache
    local user_id = cache:get("email:" .. normalized_email)
    local user_data_json = user_id and cache:get(user_id)
    
    if user_data_json then
        local cjson = require "cjson.safe"
        local user_data = cjson.decode(user_data_json)
        
        if user_data then
            ngx.var.username = user_data.username or ""
            ngx.var.display_name = user_data.display_name or ""
            ngx.var.user_id = user_data.user_uuid or user_id or ""
            user_context_headers.apply(normalized_email, groups)
            
            ngx.log(ngx.INFO, "[USER_ME] Usuário encontrado no cache: " .. 
                (user_data.username or "N/A") .. " (" .. normalized_email .. ")")
        else
            ngx.log(ngx.WARN, "[USER_ME] Erro ao decodificar dados do usuário do cache")
        end
    else
        ngx.log(ngx.WARN, "[USER_ME] Usuário não encontrado no cache para email: " .. 
            normalized_email)
    end
else
    ngx.log(ngx.WARN, "[USER_ME] Email não fornecido pelo Authelia")
end

ngx.var.myrole = is_admin and "true" or "false"
