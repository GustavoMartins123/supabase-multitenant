local cjson = require "cjson.safe"
local user_identity = require "user_identity"

local M = {}

function M.apply(email, groups)
    local normalized_email = user_identity.normalize_email(email)
    local email_hash = user_identity.hash_email(normalized_email)

    ngx.req.set_header("Remote-Email", email_hash)
    ngx.req.set_header("Remote-Groups", groups or "")
    ngx.req.set_header("X-User-Email", normalized_email)
    ngx.req.set_header("X-User-Groups", groups or "")

    local cache = ngx.shared.users_cache
    if not cache then
        return email_hash
    end

    local user_data_json = cache:get(email_hash)
    if not user_data_json then
        return email_hash
    end

    local user_data = cjson.decode(user_data_json)
    if not user_data then
        return email_hash
    end

    if user_data.username and user_data.username ~= "" then
        ngx.req.set_header("X-User-Username", user_data.username)
    end
    if user_data.display_name and user_data.display_name ~= "" then
        ngx.req.set_header("X-User-Display-Name", user_data.display_name)
    end
    if user_data.user_uuid and user_data.user_uuid ~= "" then
        ngx.req.set_header("X-User-Id", user_data.user_uuid)
    end

    return email_hash
end

return M
