local M = {}

function M.normalize_email(email)
    return (email or ""):lower():gsub("%s+", "")
end

return M
