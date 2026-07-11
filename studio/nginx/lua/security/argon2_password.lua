local ffi = require("ffi")
local random = require("resty.random")

local ARGON2_TIME_COST = 3
local ARGON2_MEMORY_KIB = 65536
local ARGON2_PARALLELISM = 4
local ARGON2_HASH_LEN = 32
local ARGON2_SALT_LEN = 16
local ARGON2_ID = 2
local ARGON2_OK = 0

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

function M.hash_password(plain_password)
    if not argon2 then
        return nil
    end

    local salt = random.bytes(ARGON2_SALT_LEN, true)
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

return M
