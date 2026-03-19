local cjson = require "cjson.safe"

local mock_subscription = {
    billing_cycle_anchor = 0,
    current_period_end = 0,
    current_period_start = 0,
    next_invoice_at = 0,
    usage_billing_enabled = false,
    plan = { 
        id = "enterprise", 
        name = "Enterprise" 
    },
    addons = {},
    project_addons = {},
    payment_method_type = "",
    billing_via_partner = false,
    billing_partner = "fly",
    scheduled_plan_change = ngx.null,
    customer_balance = 0,
    cached_egress_enabled = false
}

ngx.header.content_type = "application/json; charset=utf-8"
ngx.status = ngx.HTTP_OK
ngx.say(cjson.encode(mock_subscription))
ngx.log(ngx.INFO, "[MOCK-SUBSCRIPTION] Mock subscription returned for: ", ngx.var.authelia_email)
return ngx.exit(ngx.HTTP_OK)
