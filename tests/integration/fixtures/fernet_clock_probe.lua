-- Actual OpenResty/crypto modules; only the forbidden coarse clock is poisoned.
local cjson = require("cjson.safe")
local data = assert(cjson.decode(io.read("*a")))
local cipher = assert(require("resty.fernet"):new(data.key))
os.time = function() error("coarse wall clock must not be used") end
local calls = 0
local update = ngx.update_time
ngx.update_time = function() calls = calls + 1; update() end
assert(cipher:decrypt(data.valid) == "sb_secret_synthetic")
local key, err = cipher:decrypt(data.future)
assert(key == nil and err == "unacceptable clock skew")
key, err = cipher:decrypt(data.expired, 60)
assert(key == nil and err == "token has expired")
assert(calls == 3)
print("PASS fresh Fernet clock, Python/Lua interoperability, future denial and expiry")
