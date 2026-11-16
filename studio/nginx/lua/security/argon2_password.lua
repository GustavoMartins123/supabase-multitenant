local ffi = require("ffi")
local random = require("resty.random")

local ARGON2_TIME_COST = 3
local ARGON2_MEMORY_KIB = 65536
local ARGON2_PARALLELISM = 4
local ARGON2_HASH_LEN = 32
local ARGON2_SALT_LEN = 16
local ARGON2_ID = 2
local ARGON2_OK = 0
local MAX_ARGON2_CONCURRENCY = 4
local PIPE_TIMEOUT_MS = 15000
local LUAJIT_BIN = "/usr/local/openresty/luajit/bin/luajit"

local PIPE_HASH_SCRIPT = [[
local ffi = require("ffi")
ffi.cdef[=[
int argon2id_hash_encoded(unsigned int t_cost, unsigned int m_cost, unsigned int parallelism, const void *pwd, size_t pwdlen, const void *salt, size_t saltlen, size_t hashlen, char *encoded, size_t encodedlen);
size_t argon2_encodedlen(unsigned int t_cost, unsigned int m_cost, unsigned int parallelism, unsigned int saltlen, size_t hashlen, int type);
const char *argon2_error_message(int error_code);
]=]
local function load_lib()
    for _, candidate in ipairs({
        "argon2",
        "libargon2.so.1",
        "/usr/lib/x86_64-linux-gnu/libargon2.so.1",
        "/usr/lib/aarch64-linux-gnu/libargon2.so.1",
        "/lib/x86_64-linux-gnu/libargon2.so.1",
        "/lib/aarch64-linux-gnu/libargon2.so.1",
    }) do
        local ok, lib = pcall(ffi.load, candidate)
        if ok then return lib end
    end
    return nil
end
local lib = load_lib()
if not lib then os.exit(2) end
local salt_hex = os.getenv("ARGON2_SALT_HEX") or ""
if #salt_hex ~= 32 or not salt_hex:match("^[0-9a-fA-F]+$") then os.exit(3) end
local salt = salt_hex:gsub("..", function(cc) return string.char(tonumber(cc, 16)) end)
local pwd = io.read("*a") or ""
local len = tonumber(lib.argon2_encodedlen(3, 65536, 4, #salt, 32, 2))
if not len or len <= 0 then os.exit(4) end
local encoded = ffi.new("char[?]", len)
local rc = lib.argon2id_hash_encoded(3, 65536, 4, pwd, #pwd, salt, #salt, 32, encoded, len)
if rc ~= 0 then
    io.stderr:write(ffi.string(lib.argon2_error_message(rc)))
    os.exit(5)
end
io.write(ffi.string(encoded))
]]

ffi.cdef[[
int argon2id_hash_encoded(
    unsigned int t_cost,
    unsigned int m_cost,
    unsigned int parallelism,
    const void *pwd,
    size_t pwdlen,
    const void *salt,
    size_t saltlen,
    size_t hashlen,
    char *encoded,
    size_t encodedlen
);

size_t argon2_encodedlen(
    unsigned int t_cost,
    unsigned int m_cost,
    unsigned int parallelism,
    unsigned int saltlen,
    unsigned int hashlen,
    int type
);

const char *argon2_error_message(int error_code);
]]

local function load_argon2()
    local candidates = {
        "argon2",
        "libargon2.so.1",
        "/usr/lib/x86_64-linux-gnu/libargon2.so.1",
        "/usr/lib/aarch64-linux-gnu/libargon2.so.1",
        "/lib/x86_64-linux-gnu/libargon2.so.1",
        "/lib/aarch64-linux-gnu/libargon2.so.1",
    }

    for _, candidate in ipairs(candidates) do
        local ok, lib = pcall(ffi.load, candidate)
        if ok then
            return lib
        end
    end

    ngx.log(ngx.ERR, "[ARGON2] Failed to load libargon2")
    return nil
end

local argon2 = load_argon2()

local M = {}

local function to_hex(bytes)
    return (bytes:gsub(".", function(char)
        return string.format("%02x", string.byte(char))
    end))
end

local function acquire_slot()
    local shared = ngx and ngx.shared and ngx.shared.avatar_processing
    if not shared then
        return function() end
    end
    local deadline = (ngx.now and ngx.now() or os.time()) + 5
    while true do
        shared:add("argon2_inflight", 0, 60)
        local count = shared:incr("argon2_inflight", 1, 0)
        if count and count <= MAX_ARGON2_CONCURRENCY then
            return function()
                local next_val = shared:incr("argon2_inflight", -1, 0)
                if next_val and next_val < 0 then
                    shared:set("argon2_inflight", 0, 60)
                end
            end
        end
        shared:incr("argon2_inflight", -1, 0)
        if (ngx.now and ngx.now() or os.time()) >= deadline then
            return nil
        end
        ngx.sleep(0.02)
    end
end

local function hash_password_pipe(pipe, plain_password, salt)
    local release = acquire_slot()
    if not release then
        ngx.log(ngx.ERR, "[ARGON2] Worker concurrency limit reached")
        return nil
    end

    local proc, spawn_err = pipe.spawn({ LUAJIT_BIN, "-e", PIPE_HASH_SCRIPT }, {
        merge_stderr = false,
        buffer_size = 4096,
        write_timeout = PIPE_TIMEOUT_MS,
        stdout_read_timeout = PIPE_TIMEOUT_MS,
        stderr_read_timeout = PIPE_TIMEOUT_MS,
        wait_timeout = PIPE_TIMEOUT_MS,
        environ = {
            "PATH=/usr/local/openresty/luajit/bin:/usr/bin:/bin",
            "ARGON2_SALT_HEX=" .. to_hex(salt),
        },
    })
    if not proc then
        release()
        ngx.log(ngx.ERR, "[ARGON2] Failed to spawn worker: ", spawn_err or "unknown error")
        return nil
    end

    local written, write_err = proc:write(plain_password)
    if not written then
        proc:kill(9)
        proc:wait()
        release()
        ngx.log(ngx.ERR, "[ARGON2] Failed to write password input: ", write_err or "unknown error")
        return nil
    end
    proc:shutdown("stdin")

    local stdout, read_err, partial = proc:stdout_read_all()
    if not stdout and read_err == "closed" then
        stdout = partial or ""
    end
    local stderr = proc:stderr_read_all() or ""
    local ok, reason, status = proc:wait()
    release()

    if not stdout or ok ~= true or status ~= 0 then
        ngx.log(
            ngx.ERR,
            "[ARGON2] Worker hash failed: reason=",
            tostring(reason or read_err or "unknown"),
            " status=",
            tostring(status or ""),
            " err=",
            tostring(stderr)
        )
        return nil
    end

    local hash = stdout:gsub("[%r%n]+$", "")
    if hash == "" then
        ngx.log(ngx.ERR, "[ARGON2] Empty hash output from worker")
        return nil
    end
    return hash
end

function M.hash_password_ffi(plain_password, salt)
    if not argon2 then
        return nil
    end

    salt = salt or random.bytes(ARGON2_SALT_LEN, true)
    if not salt then
        ngx.log(ngx.ERR, "[ARGON2] Failed to generate salt")
        return nil
    end

    local encoded_len = tonumber(argon2.argon2_encodedlen(
        ARGON2_TIME_COST,
        ARGON2_MEMORY_KIB,
        ARGON2_PARALLELISM,
        ARGON2_SALT_LEN,
        ARGON2_HASH_LEN,
        ARGON2_ID
    ))
    if not encoded_len or encoded_len <= 0 then
        ngx.log(ngx.ERR, "[ARGON2] Failed to calculate encoded length")
        return nil
    end

    local encoded = ffi.new("char[?]", encoded_len)
    local result = argon2.argon2id_hash_encoded(
        ARGON2_TIME_COST,
        ARGON2_MEMORY_KIB,
        ARGON2_PARALLELISM,
        plain_password,
        #plain_password,
        salt,
        ARGON2_SALT_LEN,
        ARGON2_HASH_LEN,
        encoded,
        encoded_len
    )

    if result ~= ARGON2_OK then
        local err = argon2.argon2_error_message(result)
        ngx.log(
            ngx.ERR,
            "[ARGON2] Hash failed: ",
            err ~= nil and ffi.string(err) or tostring(result)
        )
        return nil
    end

    local hash = ffi.string(encoded)
    if hash == "" then
        ngx.log(ngx.ERR, "[ARGON2] Empty hash output")
        return nil
    end

    return hash
end

function M.hash_password(plain_password)
    if type(plain_password) ~= "string" then
        return nil
    end
    local salt = random.bytes(ARGON2_SALT_LEN, true)
    if not salt then
        ngx.log(ngx.ERR, "[ARGON2] Failed to generate salt")
        return nil
    end

    local ok_pipe, pipe = pcall(require, "ngx.pipe")
    if ok_pipe and pipe and type(pipe.spawn) == "function" then
        return hash_password_pipe(pipe, plain_password, salt)
    end

    return M.hash_password_ffi(plain_password, salt)
end

return M
