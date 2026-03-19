local cjson = require "cjson.safe"

local email = ngx.var.authelia_email or "billing@example.com"
local org_name = os.getenv("DEFAULT_ORGANIZATION_NAME") or "Default Organization"
local org_slug = os.getenv("DEFAULT_ORGANIZATION_SLUG") or "default-org-slug"

local default_opt_in_tags = {
    "AI_SQL_GENERATOR_OPT_IN",
    "AI_LOG_GENERATOR_OPT_IN",
    "AI_DATA_GENERATOR_OPT_IN"
}

if ngx.var.request_method == "GET" then
    local org_data = {
        id = 1,
        name = org_name,
        slug = org_slug,
        billing_email = email,
        plan = { 
            id = "enterprise", 
            name = "Enterprise" 
        },
        opt_in_tags = default_opt_in_tags
    }
    
    local response_array = { org_data }
    
    ngx.header.content_type = "application/json; charset=utf-8"
    ngx.status = ngx.HTTP_OK
    ngx.say(cjson.encode(response_array))
    ngx.log(ngx.INFO, "[MOCK-ORGANIZATIONS] GET for: ", email)
    return ngx.exit(ngx.HTTP_OK)

elseif ngx.var.request_method == "PATCH" then
    ngx.req.read_body()
    local body = ngx.req.get_body_data()
    local request_data = cjson.decode(body) or {}
    
    local opt_in_tags = request_data.opt_in_tags or default_opt_in_tags
    
    local org_data = {
        id = 1,
        name = org_name,
        slug = org_slug,
        billing_email = email,
        plan = { 
            id = "enterprise", 
            name = "Enterprise" 
        },
        opt_in_tags = opt_in_tags
    }
    
    ngx.header.content_type = "application/json; charset=utf-8"
    ngx.status = ngx.HTTP_OK
    ngx.say(cjson.encode(org_data))
    ngx.log(ngx.INFO, "[MOCK-ORGANIZATIONS] PATCH. Tags: ", cjson.encode(opt_in_tags))
    return ngx.exit(ngx.HTTP_OK)

else
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.header["Allow"] = "GET, PATCH"
    ngx.say('{"error": "Method Not Allowed"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end
