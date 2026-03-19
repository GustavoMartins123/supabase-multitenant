local pgmoon = require("pgmoon")
local cjson = require("cjson.safe")

local _M = {}

local function parse_database_url(url)
    if not url or url == "" then return nil end
    local user, pass, host, port, db =
        url:match("^postgresql?://([^:]+):([^@]+)@([^:]+):(%d+)/(.+)$")
    if not user then
        user, pass, host, db = url:match("^postgresql?://([^:]+):([^@]+)@([^/]+)/(.+)$")
        port = "5432"
    end
    if not user then return nil end
    return {
        host     = host,
        port     = tonumber(port) or 5432,
        database = db,
        user     = user,
        password = pass
    }
end

local DB_CONFIG = parse_database_url(os.getenv("DATABASE_URL")) or {
    host     = "postgres",
    port     = 5432,
    database = os.getenv("POSTGRES_DB")       or "nginx",
    user     = os.getenv("POSTGRES_USER")     or "nginx_user",
    password = os.getenv("POSTGRES_NGINX_PASSWORD")
}

function _M.connect()
    local pg = pgmoon.new(DB_CONFIG)
    local success, err = pg:connect()
    if not success then
        ngx.log(ngx.ERR, "[DB] Connection failed: ", err)
        return nil, err
    end
    return pg
end

function _M.get_or_create_session(user_id, project_ref, session_id)
    local pg, err = _M.connect()
    if not pg then return nil, err end
    
    local query = string.format(
        "SELECT get_or_create_session(%s, %s, %s)",
        pg:escape_literal(user_id),
        pg:escape_literal(project_ref),
        session_id and pg:escape_literal(session_id) or "NULL"
    )
    
    ngx.log(ngx.INFO, "[DB] Query: ", query)
    
    local result, err = pg:query(query)
    pg:keepalive(10000, 50)
    
    if not result then
        ngx.log(ngx.ERR, "[DB] Session query failed: ", err)
        return nil, err
    end
    
    return result[1].get_or_create_session
end

function _M.get_recent_messages(session_id, limit)
    local pg, err = _M.connect()
    if not pg then return nil, err end
    
    limit = limit or 10
    
    local query = string.format(
        "SELECT * FROM get_recent_messages(%s, %d) ORDER BY created_at ASC",
        pg:escape_literal(session_id),
        limit
    )
    
    local result, err = pg:query(query)
    pg:keepalive(10000, 50)
    
    if not result then
        ngx.log(ngx.ERR, "[DB] Messages query failed: ", err)
        return nil, err
    end
    
    return result
end

function _M.save_message(session_id, role, content, model_used)
    local pg, err = _M.connect()
    if not pg then return nil, err end
    
    local query = string.format(
        "SELECT save_message(%s, %s, %s, %s)",
        pg:escape_literal(session_id),
        pg:escape_literal(role),
        pg:escape_literal(content),
        model_used and pg:escape_literal(model_used) or "NULL"
    )
    
    local result, err = pg:query(query)
    pg:keepalive(10000, 50)
    
    if not result then
        ngx.log(ngx.ERR, "[DB] Save message failed: ", err)
        return nil, err
    end
    
    return result[1].save_message
end

return _M