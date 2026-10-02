local fernet = require("resty.fernet")
local _M = {}

function _M.load(context)
    if type(context.enc_admin_key) ~= "string" or context.enc_admin_key == "" then
        ngx.status = ngx.HTTP_FORBIDDEN
        ngx.say('{"error":"administrative_access_required"}')
        return ngx.exit(ngx.HTTP_FORBIDDEN)
    end
    local ok, cipher = pcall(fernet.new, fernet, os.getenv("STUDIO_SERVICE_KEY_ENCRYPTION_KEY"))
    local decrypted, key
    if ok and cipher then
        decrypted, key = pcall(cipher.decrypt, cipher, context.enc_admin_key)
    end
    if not decrypted or type(key) ~= "string" or not key:match("^sb_secret_") then
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.say('{"error":"administrative_credential_unavailable"}')
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
    return key
end

return _M
