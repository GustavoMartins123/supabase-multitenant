local cjson = require("cjson.safe")
local user_identity = require("project_context.user_identity")
local login_session = require("security.login_session")
local user_hmac_token = require("security.user_hmac_token")

local M = {}

function M.apply(email, groups)
    local canonical, err = require("admin_api.directory_snapshot").for_email(email)
    if not canonical then
        ngx.log(ngx.ERR, "[AUTH] Canonical directory unavailable: ", err)
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
    local entry = canonical.user
    if not entry.is_active then return ngx.exit(ngx.HTTP_FORBIDDEN) end
    groups = table.concat(entry.groups, ",")
    ngx.ctx.canonical_groups = groups
    local user_id = entry.id
    local user_data = {username=entry.username, display_name=entry.display_name, user_uuid=entry.id}

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
        local session_fingerprint, fingerprint_err = login_session.fingerprint()
        if fingerprint_err then
            ngx.log(ngx.ERR, "[AUTH] Falha ao calcular fingerprint da sessao: ", fingerprint_err)
        end
        local token, token_err = user_hmac_token.sign(user_id, {
            username = user_data and user_data.username or nil,
            display_name = user_data and user_data.display_name or nil,
            groups = groups or "",
            directory_revision = canonical.revision,
            login_session = session_fingerprint,
        })
        if token then
            ngx.req.set_header("X-User-Token", token)
            pcall(function()
                ngx.var.auth_user_token = token
            end)
        else
            ngx.log(ngx.ERR, "[AUTH] Falha ao assinar token de usuario: ", token_err or "erro desconhecido")
            return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
        end
    end

    return user_id, groups, entry
end

return M
