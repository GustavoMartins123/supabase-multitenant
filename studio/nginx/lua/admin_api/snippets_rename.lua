-- Renomeia as pastas de snippets SQL do usuario quando um projeto muda de slug.
--
-- Os snippets do Studio (SNIPPETS_MANAGEMENT_FOLDER) sao guardados em diretorios
-- nomeados "<user_id>__<slug>" (raiz) e "<user_id>__<slug>__<sub>" (subpastas).
-- Quando o projeto e renomeado, esses diretorios precisam migrar para o novo
-- slug, senao os snippets ficam orfaos e "somem" do front. O projects-api chama
-- este endpoint (mesma auth do invalidate_service_key) apos concluir o rename.
local cjson = require("cjson")
local cjson_safe = require("cjson.safe")
local lfs = require("lfs")
local shared_token = require("security.shared_token")

local SNIPPETS_DIR = os.getenv("SNIPPETS_MANAGEMENT_FOLDER") or "/app/snippets"

local function forbidden()
    return ngx.exit(ngx.HTTP_FORBIDDEN)
end

local headers = ngx.req.get_headers()
local supplied_token = headers["X-Shared-Token"] or ""
local internal_service = headers["X-Internal-Service"]

if internal_service ~= "projects-api" or not shared_token.matches(supplied_token) then
    return forbidden()
end
if ngx.req.get_method() ~= "POST" then
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

local function valid_name(name)
    if type(name) ~= "string" then
        return false
    end
    return ngx.re.match(name, [[^[a-z_][a-z0-9_]{2,39}$]], "jo") ~= nil
end

ngx.req.read_body()
local body = cjson_safe.decode(ngx.req.get_body_data() or "{}") or {}
local old_name = body.old_name
local new_name = body.new_name

if not valid_name(old_name) or not valid_name(new_name) or old_name == new_name then
    return ngx.exit(ngx.HTTP_BAD_REQUEST)
end

-- Diretorio inexistente: nada a migrar (idempotente).
if not lfs.attributes(SNIPPETS_DIR, "mode") then
    ngx.header.content_type = "application/json"
    ngx.say(cjson.encode({ renamed = 0, errors = {} }))
    return
end

-- Coleta primeiro; so renomeia depois de fechar o iterador do lfs.dir para nao
-- invalidar a enumeracao ao mexer no proprio diretorio.
local planned = {}
for entry in lfs.dir(SNIPPETS_DIR) do
    if entry ~= "." and entry ~= ".." then
        local full = SNIPPETS_DIR .. "/" .. entry
        if lfs.attributes(full, "mode") == "directory" then
            -- O user_id (UUID) nao contem "__", entao o primeiro "__" separa o
            -- user_id do escopo ("<slug>" ou "<slug>__<sub>").
            local _, sep_end = entry:find("__", 1, true)
            if sep_end then
                local prefix = entry:sub(1, sep_end)
                local scope = entry:sub(sep_end + 1)
                local new_scope
                if scope == old_name then
                    new_scope = new_name
                elseif scope:sub(1, #old_name + 2) == old_name .. "__" then
                    new_scope = new_name .. scope:sub(#old_name + 1)
                end
                if new_scope then
                    table.insert(planned, {
                        from = full,
                        to = SNIPPETS_DIR .. "/" .. prefix .. new_scope,
                        label = entry,
                    })
                end
            end
        end
    end
end

local renamed = 0
local errors = {}

for _, item in ipairs(planned) do
    if lfs.attributes(item.to, "mode") then
        local message = "destino ja existe: " .. item.to
        ngx.log(ngx.ERR, "[SNIPPETS-RENAME] ", message)
        table.insert(errors, message)
    else
        local ok, err = os.rename(item.from, item.to)
        if ok then
            renamed = renamed + 1
        else
            local message = item.label .. ": " .. (err or "rename falhou")
            ngx.log(ngx.ERR, "[SNIPPETS-RENAME] ", message)
            table.insert(errors, message)
        end
    end
end

ngx.header.content_type = "application/json"
ngx.say(cjson.encode({
    renamed = renamed,
    errors = setmetatable(errors, cjson.array_mt),
}))
