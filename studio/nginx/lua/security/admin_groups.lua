local M = {}

local function trim(value)
    return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function configured_admin_groups()
    local configured = os.getenv("ADMIN_GROUPS") or "admin"
    local allowed = {}

    for token in (configured .. ","):gmatch("(.-),") do
        local group = trim(token):lower()
        if group ~= "" then
            allowed[group] = true
        end
    end

    if next(allowed) == nil then
        ngx.log(ngx.ERR, "[ADMIN] ADMIN_GROUPS nao contem nenhum grupo valido")
    end
    return allowed
end

local ADMIN_GROUPS = configured_admin_groups()

local function malformed(groups, reason)
    ngx.log(
        ngx.WARN,
        "[ADMIN] Header Remote-Groups em formato inesperado: ",
        reason,
        "; valor=",
        groups
    )
    return nil
end

function M.parse(groups)
    if type(groups) ~= "string" then
        return malformed(tostring(groups), "tipo invalido")
    end

    local value = trim(groups)
    if value == "" then
        return {}
    end

    local opens = value:sub(1, 1) == "["
    local closes = value:sub(-1) == "]"
    if opens ~= closes then
        return malformed(groups, "colchetes desbalanceados")
    end
    if opens then
        value = trim(value:sub(2, -2))
    end
    if value:find("[%[%]]") then
        return malformed(groups, "colchete em posicao invalida")
    end
    if value:find("[;\"']") then
        return malformed(groups, "separador ou aspas nao suportados")
    end
    if value == "" then
        return {}
    end

    local parsed = {}
    for token in (value .. ","):gmatch("(.-),") do
        local group = trim(token):lower()
        if group == "" then
            return malformed(groups, "grupo vazio")
        end
        parsed[#parsed + 1] = group
    end
    return parsed
end

function M.is_admin(groups)
    local parsed = M.parse(groups)
    if not parsed then
        return false
    end

    for _, group in ipairs(parsed) do
        if ADMIN_GROUPS[group] then
            return true
        end
    end
    return false
end

return M
