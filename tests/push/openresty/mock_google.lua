-- Test-only upstream transport. Loaded before production modules in an isolated
-- nginx with no external network. Uses real OpenSSL JWT signing and resty.lock.
local cjson=require("cjson.safe")
package.loaded["push_test_real_http"]=require("resty.http")
package.loaded["resty.http"]={new=function()
    return {set_timeouts=function() end,request_uri=function(_,uri,opts)
        assert(opts.ssl_verify==true,"outbound TLS must be verified")
        local stats=ngx.shared.test_stats
        if uri=="https://oauth2.googleapis.com/token" then
            stats:incr("oauth_calls",1,0)
            assert(opts.body:find("assertion="))
            ngx.sleep(stats:get("oauth_delay") or .04)
            if stats:get("oauth_mode")=="throw" then error("secret-upstream-access private-key internal-test-secret") end
            if stats:get("oauth_mode")=="fail" then return {status=503,body="secret-upstream-access"} end
            return {status=200,body=cjson.encode({access_token="secret-oauth-access",expires_in=stats:get("expires") or 3600})}
        end
        assert(uri=="https://fcm.googleapis.com/v1/projects/shared-test/messages:send")
        assert(opts.headers.Authorization=="Bearer secret-oauth-access")
        stats:incr("fcm_calls",1,0)
        ngx.sleep(.04)
        local token=cjson.decode(opts.body).message.token
        if token=="unregistered" or token=="invalid" then
            return {status=token=="unregistered" and 404 or 400,
                body=cjson.encode({error={message="secret-fcm-token",details={{
                    ["@type"]="type.googleapis.com/google.firebase.fcm.v1.FcmError",
                    errorCode=token=="unregistered" and "UNREGISTERED" or "INVALID_ARGUMENT"}}}})}
        end
        if token=="rate" then return {status=429,headers={["Retry-After"]="120"},body='{"error":{}}'} end
        if token=="network" then return nil,"secret-fcm-token network" end
        return {status=200,body='{"name":"projects/shared-test/messages/accepted"}'}
    end}
end}
