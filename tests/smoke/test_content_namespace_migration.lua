local lfs = require("lfs")

local root = assert(os.getenv("SNIPPETS_TEST_DIR"), "SNIPPETS_TEST_DIR is required")
local user_id = "5dae1152-7b44-4351-8dab-5e08574dcba4"
local project_id = "26cb6971-f9ef-4890-a924-92179b97f189"

local values = {}
local expirations = {}
local now = 1000
local cache = {}

function cache:get(key)
    local expires = expirations[key]
    if expires and expires <= now then
        values[key] = nil
        expirations[key] = nil
    end
    return values[key]
end

function cache:set(key, value, ttl)
    values[key] = value
    expirations[key] = ttl and (now + ttl) or nil
    return true
end

function cache:add(key, value, ttl)
    if self:get(key) ~= nil then
        return nil, "exists"
    end
    return self:set(key, value, ttl)
end

function cache:delete(key)
    values[key] = nil
    expirations[key] = nil
    return true
end

ngx = {
    shared = { service_keys = cache },
    WARN = "WARN",
    NOTICE = "NOTICE",
    now = function() return now end,
    sleep = function(seconds) now = now + seconds end,
    log = function(...) end,
}

package.path = table.concat({
    "studio/nginx/lua/?.lua",
    "studio/nginx/lua/?/init.lua",
    package.path,
}, ";")

local function join(left, right)
    return left .. "/" .. right
end

local function mkdir(path)
    local ok, err = lfs.mkdir(path)
    assert(ok or lfs.attributes(path, "mode") == "directory", err)
end

local function write(path, content)
    local file = assert(io.open(path, "wb"))
    file:write(content)
    file:close()
end

local function read(path)
    local file = assert(io.open(path, "rb"))
    local content = file:read("*a")
    file:close()
    return content
end

local old_root = join(root, user_id .. "__meu_projeto")
local new_root = join(root, user_id .. "__outro_projeto")
local old_child = join(root, user_id .. "__meu_projeto__relatorios")
local new_child = join(root, user_id .. "__outro_projeto__relatorios")
local stable_root = join(root, user_id .. "__" .. project_id)
local stable_child = join(root, user_id .. "__" .. project_id .. "__relatorios")

mkdir(old_root)
mkdir(new_root)
mkdir(old_child)
mkdir(new_child)

write(join(old_root, "query.sql"), "select 'old';\n")
write(join(new_root, "query.sql"), "select 'new';\n")
write(join(old_root, "same.sql"), "select 1;\n")
write(join(new_root, "same.sql"), "select 1;\n")
write(join(old_child, "child.sql"), "select 'old child';\n")
write(join(new_child, "child.sql"), "select 'new child';\n")

local migration = require("studio_compat.content_namespace_migration")
local ok, stats = migration.ensure(user_id, {
    project_id = project_id,
    current_ref = "outro_projeto",
    aliases = { "outro_projeto", "meu_projeto" },
})
assert(ok, stats)

assert(lfs.attributes(stable_root, "mode") == "directory")
assert(lfs.attributes(stable_child, "mode") == "directory")
assert(lfs.attributes(old_root, "mode") == nil)
assert(lfs.attributes(new_root, "mode") == nil)
assert(lfs.attributes(old_child, "mode") == nil)
assert(lfs.attributes(new_child, "mode") == nil)

assert(read(join(stable_root, "query.sql")) == "select 'old';\n")
assert(read(join(stable_root, "query__legacy_outro_projeto.sql")) == "select 'new';\n")
assert(read(join(stable_root, "same.sql")) == "select 1;\n")
assert(lfs.attributes(join(stable_root, "same__legacy_outro_projeto.sql"), "mode") == nil)
assert(read(join(stable_child, "child.sql")) == "select 'old child';\n")
assert(
    read(join(stable_child, "child__legacy_outro_projeto.sql"))
        == "select 'new child';\n"
)
assert(stats.conflicts_preserved == 2)
assert(stats.identical_duplicates == 1)

local second_ok, second_stats = migration.ensure(user_id, {
    project_id = project_id,
    current_ref = "outro_projeto",
    aliases = { "outro_projeto", "meu_projeto" },
})
assert(second_ok)
assert(second_stats == nil)

print("content namespace migration test passed")
