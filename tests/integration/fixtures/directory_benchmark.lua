-- Real production snapshot/locking/YAML code, synthetic persisted identities.
local cjson = require("cjson.safe")
local yaml = require("lyaml")
local original_load = yaml.load
local parses = 0
yaml.load = function(...) parses = parses + 1; return original_load(...) end
local store = require("admin_api.authelia_user_store")
local snapshot = require("admin_api.directory_snapshot")
local measurements = {}
local expected = assert(tonumber(os.getenv("DIRECTORY_BENCHMARK_USERS")))
for _ = 1, 5 do
    parses = 0
    ngx.update_time()
    local start = ngx.now()
    local result, err = store.with_lock(function() return snapshot.read_locked(false) end)
    ngx.update_time()
    assert(result, err)
    assert(#result.users == expected)
    for _, user in ipairs(result.users) do assert(user.is_active and user.id ~= "") end
    measurements[#measurements + 1] = {milliseconds = (ngx.now() - start) * 1000, yaml_parses = parses}
end
print(cjson.encode({users = expected, measurements = measurements}))
