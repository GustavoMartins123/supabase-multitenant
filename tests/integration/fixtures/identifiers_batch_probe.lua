-- Real file store/lock/identity reader; no exported-identity or authorization mocks.
local cjson = require("cjson.safe")
local files = require("admin_api.authelia_file_store")
local identifiers = require("admin_api.authelia_identifiers")
local acquire = files.acquire
local locks = 0
files.acquire = function(resource)
    if resource == "ids.yml" then locks = locks + 1 end
    return acquire(resource)
end
local path = "/config/ids.yml"
local function write(content)
    local file = assert(io.open(path, "wb")); assert(file:write(content)); file:close()
end
local first = {username="probe_a",service="openid",sector="",identifier="11111111-1111-4111-8111-111111111111"}
local second = {username="probe_b",service="openid",sector="",identifier="22222222-2222-4222-8222-222222222222"}
write(cjson.encode({identifiers={first,second}}))
local result, created, err = identifiers.ensure_identifiers({"probe_a","probe_b"})
assert(result, err); assert(result.probe_a == first.identifier and result.probe_b == second.identifier)
assert(created.probe_a == false and created.probe_b == false and locks == 1)
first.identifier="33333333-3333-4333-8333-333333333333"
write(cjson.encode({identifiers={first,second}}))
result, _, err = identifiers.ensure_identifiers({"probe_a","probe_b"})
assert(result, err); assert(result.probe_a == first.identifier and locks == 2)
assert(identifiers.ensure_identifier("probe_a") == first.identifier)
assert(identifiers.ensure_identifier(nil) == nil)
assert(identifiers.ensure_identifiers({"probe_a", "probe_a"}) == nil)
assert(identifiers.ensure_identifiers({not_a_list="probe_a"}) == nil)
assert(identifiers.ensure_identifiers({[1]="probe_a",[3]="probe_b",[4]="probe_c"}) == nil)
for _, invalid in ipairs({"", "not: [valid", "{}", '{"identifiers":{"not_a_list":{}}}',
                           cjson.encode({identifiers={first,first}}),
                           cjson.encode({identifiers={first,{username="probe_c",service="openid",identifier=first.identifier}}})}) do
    write(invalid)
    result, _, err = identifiers.ensure_identifiers({"probe_a"})
    assert(result == nil and type(err) == "string")
end
assert(os.remove(path))
result, _, err = identifiers.ensure_identifiers({"probe_a"})
assert(result == nil and type(err) == "string")
print("PASS single-lock identity batch, fresh edits, invalid/duplicate/missing identity denial")
