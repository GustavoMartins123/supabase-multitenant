local cjson = require('cjson')

local function reject(status, message)
    ngx.status = status
    ngx.header['Content-Type'] = 'application/json'
    ngx.say(cjson.encode({error = 'client_configuration_error', message = message}))
    return ngx.exit(status)
end

local ref = ngx.var.uri:match('^/config/([a-z]+)$')
if not ref or #ref ~= 20 or ngx.var.request_uri ~= '/config/' .. ref then
    return reject(400, 'Invalid application configuration reference')
end
local method = ngx.req.get_method()
if method == 'OPTIONS' then
    return ngx.exit(204)
end
if method ~= 'GET' then
    ngx.header['Allow'] = 'GET, OPTIONS'
    return reject(405, 'Only GET and OPTIONS are allowed')
end
if ngx.var.http_transfer_encoding or (ngx.var.http_content_length and ngx.var.http_content_length ~= '0') then
    return reject(400, 'Configuration requests must not contain a body')
end

require('security.projects_api_signer').enforce()
