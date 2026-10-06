local M = {}

local FORGEABLE_HEADERS = {
    -- Familia auth_request do Authelia.
    "Remote-User",
    "Remote-Email",
    "Remote-Name",
    "Remote-Groups",
    -- Identidade emitida pelo proprio gateway para o control plane.
    "X-User-Token",
    "X-User-Id",
    "X-User-Groups",
    "X-User-Username",
    "X-User-Display-Name",
}

function M.strip()
    if ngx.is_subrequest then
        return
    end
    for _, name in ipairs(FORGEABLE_HEADERS) do
        ngx.req.clear_header(name)
    end
end

-- Exportado para os testes de contrato.
M.FORGEABLE_HEADERS = FORGEABLE_HEADERS

return M
