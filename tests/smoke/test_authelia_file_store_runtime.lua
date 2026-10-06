local ffi = require("ffi")
ffi.cdef[[
int usleep(unsigned int usec);
int getpid(void);
]]

local function sleep(seconds)
    ffi.C.usleep(math.floor(seconds * 1000000))
end

_G.ngx = {
    ERR = 3,
    CRIT = 2,
    now = function()
        return os.time()
    end,
    sleep = sleep,
    log = function(...) end,
    worker = {
        pid = function()
            return tonumber(ffi.C.getpid())
        end,
    },
}

package.path = table.concat({
    "./studio/nginx/lua/?.lua",
    "./studio/nginx/lua/?/init.lua",
    package.path,
}, ";")

local file_store = require("admin_api.authelia_file_store")
local target = assert(arg[1], "target path required")
local marker = assert(arg[2], "marker required")
local hold = tonumber(arg[3] or "0") or 0

local result, err = file_store.with_lock("users_database.yml", function()
    local handle = io.open(target, "rb")
    local current = ""
    if handle then
        current = handle:read("*a") or ""
        handle:close()
    end

    if hold > 0 then
        sleep(hold)
    end

    return file_store.atomic_write(target, current .. marker .. "\n", 384)
end)

if not result then
    io.stderr:write(tostring(err or "lock/write failed"), "\n")
    os.exit(1)
end
