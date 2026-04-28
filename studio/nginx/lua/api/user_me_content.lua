local cjson = require "cjson.safe"

local response = {
    is_admin = ngx.var.myrole == "true",
    username = ngx.var.username or "",
    display_name = ngx.var.display_name or "",
    user_id = ngx.var.user_id or ngx.var.user_hash or "",
    user_hash = ngx.var.user_hash or ""
}

ngx.header.content_type = "application/json"
ngx.say(cjson.encode(response))

ngx.log(ngx.INFO, "[USER_ME] Resposta enviada: " .. cjson.encode(response))
