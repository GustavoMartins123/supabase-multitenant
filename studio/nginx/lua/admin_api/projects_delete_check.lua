if ngx.var.request_method ~= "DELETE" then
    ngx.status = ngx.HTTP_METHOD_NOT_ALLOWED
    ngx.say('{"error": "Method not allowed - use DELETE"}')
    return ngx.exit(ngx.HTTP_METHOD_NOT_ALLOWED)
end

ngx.log(
    ngx.INFO,
    "[DELETE_PROJECT] Global admin accepted; backend step-up is still required"
)
