local cjson = require "cjson.safe"
local user_identity = require "user_identity"
local user_hmac_token = require "user_hmac_token"

local M = {}

function M.apply(email, groups)
    local normalized_email = user_identity.normalize_email(email)
    local cache = ngx.shared.users_cache
    local user_id = ""
    local user_data

    if cache then
        user_id = cache:get("email:" .. normalized_email) or ""
        if user_id ~= "" then
            local user_data_json = cache:get(user_id)
            if user_data_json then
                user_data = cjson.decode(user_data_json)
            end
        end
    end

    if user_data and user_data.user_uuid and user_data.user_uuid ~= "" then
        user_id = user_data.user_uuid
    end

    ngx.req.set_header("Remote-Groups", groups or "")
    ngx.req.set_header("X-User-Groups", groups or "")

    if user_data and user_data.username and user_data.username ~= "" then
        ngx.req.set_header("X-User-Username", user_data.username)
    end
    if user_data and user_data.display_name and user_data.display_name ~= "" then
        ngx.req.set_header("X-User-Display-Name", user_data.display_name)
    end
    if user_id ~= "" then
        pcall(function()
            ngx.var.auth_user_id = user_id
        end)
        local token, token_err = user_hmac_token.sign(user_id, {
            username = user_data and user_data.username or nil,
            display_name = user_data and user_data.display_name or nil,
            groups = groups or "",
        })
        if token then
            ngx.req.set_header("X-User-Token", token)
            pcall(function()
                ngx.var.auth_user_token = token
            end)
        else
            ngx.log(ngx.ERR, "[AUTH] Falha ao assinar token de usuario: ", token_err or "erro desconhecido")
        end
    end

    return user_id
end

return M
