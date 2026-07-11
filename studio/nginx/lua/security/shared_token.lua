local bit = require("bit")

local expected_token = os.getenv("NGINX_SHARED_TOKEN") or ""

local M = {}

function M.matches(supplied_token)
    supplied_token = supplied_token or ""
    if expected_token == "" or #supplied_token ~= #expected_token then
        return false
    end

    local difference = 0
    for index = 1, #expected_token do
        difference = bit.bor(
            difference,
            bit.bxor(expected_token:byte(index), supplied_token:byte(index))
        )
    end
    return difference == 0
end

return M
