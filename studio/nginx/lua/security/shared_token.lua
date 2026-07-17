local secure_compare = require("security.secure_compare")

local expected_token = os.getenv("NGINX_SHARED_TOKEN") or ""

local M = {}

function M.matches(supplied_token)
    supplied_token = supplied_token or ""
    if expected_token == "" then
        return false
    end
    return secure_compare.equals(expected_token, supplied_token)
end

return M
