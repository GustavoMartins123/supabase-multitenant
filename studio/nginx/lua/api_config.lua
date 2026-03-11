local cjson = require "cjson"
ngx.say(cjson.encode({
    server_domain = os.getenv("SERVER_DOMAIN") or "",
}))
