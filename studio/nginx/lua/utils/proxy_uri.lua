local _M = {}

function _M.escape_path(path)
    return (path:gsub("[^/]+", function(segment)
        return ngx.escape_uri(segment)
    end))
end

return _M
