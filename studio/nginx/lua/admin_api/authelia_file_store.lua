local bit = require("bit")
local ffi = require("ffi")

ffi.cdef[[
typedef long ssize_t;
int open(const char *pathname, int flags, ...);
ssize_t write(int fd, const void *buf, size_t count);
int fsync(int fd);
int flock(int fd, int operation);
int close(int fd);
int fchmod(int fd, unsigned int mode);
int chmod(const char *pathname, unsigned int mode);
]]

local M = {}

local LOCK_DIR = "/config"
local LOCK_WAIT_SECONDS = 10
local LOCK_RETRY_SECONDS = 0.02
local LOCK_FILE_MODE = 384 -- 0600
local DEFAULT_MODE = 438 -- 0666; /config e compartilhado com o container Authelia.

-- Linux flags usados pela imagem Debian do OpenResty.
local O_RDONLY = 0
local O_WRONLY = 1
local O_RDWR = 2
local O_CREAT = 64
local O_EXCL = 128
local O_NOFOLLOW = 131072
local O_DIRECTORY = 65536
local O_CLOEXEC = 524288
local LOCK_EX = 2
local LOCK_NB = 4
local LOCK_UN = 8
local EINTR = 4
local EAGAIN = 11 -- EWOULDBLOCK no Linux.
local sequence = 0

local function next_sequence()
    sequence = sequence + 1
    if sequence > 1000000000 then
        sequence = 1
    end
    return sequence
end

local function lock_path(resource)
    local clean = tostring(resource or ""):gsub("[^%w%._%-]", "_")
    -- Nao deixa o nome do lock conter o basename YAML completo; o watcher
    -- observa close_write/moved_to em /config e so deve reagir ao arquivo final.
    clean = clean:gsub("%.yml$", "")
    if clean == "" then
        return nil, "Authelia mutation lock resource is empty"
    end
    return LOCK_DIR .. "/.authelia-" .. clean .. ".lock"
end

local function close_fd(fd)
    if fd ~= nil and fd >= 0 then
        ffi.C.close(fd)
    end
end

local function write_all(fd, content)
    local offset = 0
    local length = #content
    while offset < length do
        local chunk = content:sub(offset + 1)
        local written = ffi.C.write(fd, chunk, #chunk)
        if written < 0 then
            local errno = ffi.errno()
            if errno ~= EINTR then
                return nil, "write failed errno=" .. tostring(errno)
            end
        elseif written == 0 then
            return nil, "write returned zero bytes"
        else
            offset = offset + tonumber(written)
        end
    end
    return true
end

local function parent_directory(path)
    return tostring(path):match("^(.*)/[^/]+$") or "."
end

local function fsync_parent_directory(path)
    local directory = parent_directory(path)
    local flags = bit.bor(O_RDONLY, O_DIRECTORY, O_CLOEXEC)
    local fd = ffi.C.open(directory, flags)
    if fd < 0 then
        return nil,
            "failed to open parent directory "
            .. directory
            .. " errno="
            .. tostring(ffi.errno())
    end

    if ffi.C.fsync(fd) ~= 0 then
        local errno = ffi.errno()
        close_fd(fd)
        return nil,
            "failed to fsync parent directory "
            .. directory
            .. " errno="
            .. tostring(errno)
    end

    close_fd(fd)
    return true
end

function M.acquire(resource)
    local path, path_err = lock_path(resource)
    if not path then
        return nil, path_err
    end

    local flags = bit.bor(O_RDWR, O_CREAT, O_NOFOLLOW, O_CLOEXEC)
    -- open() e variadica; no LuaJIT o mode precisa ser cdata inteiro para
    -- seguir a ABI C em vez de ser enviado como double.
    local open_mode = ffi.new("unsigned int", LOCK_FILE_MODE)
    local fd = ffi.C.open(path, flags, open_mode)
    if fd < 0 then
        return nil,
            "failed to open Authelia mutation lock "
            .. path
            .. " errno="
            .. tostring(ffi.errno())
    end

    if ffi.C.fchmod(fd, LOCK_FILE_MODE) ~= 0 then
        local errno = ffi.errno()
        close_fd(fd)
        return nil,
            "failed to secure Authelia mutation lock "
            .. path
            .. " errno="
            .. tostring(errno)
    end

    local deadline = ngx.now() + LOCK_WAIT_SECONDS
    local operation = bit.bor(LOCK_EX, LOCK_NB)
    while true do
        if ffi.C.flock(fd, operation) == 0 then
            return { fd = fd, path = path }
        end

        local errno = ffi.errno()
        if errno ~= EAGAIN and errno ~= EINTR then
            close_fd(fd)
            return nil,
                "failed to acquire Authelia mutation lock "
                .. path
                .. " errno="
                .. tostring(errno)
        end

        if ngx.now() >= deadline then
            close_fd(fd)
            return nil, "Authelia mutation is busy: " .. tostring(resource)
        end
        ngx.sleep(LOCK_RETRY_SECONDS)
    end
end

function M.release(lock)
    if not lock or type(lock.fd) ~= "number" then
        return
    end

    local fd = lock.fd
    lock.fd = nil
    if ffi.C.flock(fd, LOCK_UN) ~= 0 then
        ngx.log(
            ngx.ERR,
            "[AUTHELIA-STORE] failed to unlock ",
            tostring(lock.path),
            " errno=",
            tostring(ffi.errno())
        )
    end
    close_fd(fd)
end

function M.with_lock(resource, callback)
    local lock, lock_err = M.acquire(resource)
    if not lock then
        return nil, lock_err
    end

    local ok, a, b, c, d = pcall(callback)
    M.release(lock)

    if not ok then
        ngx.log(
            ngx.ERR,
            "[AUTHELIA-STORE] mutation failed for ",
            tostring(resource),
            ": ",
            tostring(a)
        )
        return nil, "unexpected Authelia mutation failure"
    end

    return a, b, c, d
end

function M.chmod(path, mode)
    local result = ffi.C.chmod(path, mode or DEFAULT_MODE)
    if result ~= 0 then
        return nil,
            "chmod failed for "
            .. tostring(path)
            .. " errno="
            .. tostring(ffi.errno())
    end
    return true
end

function M.atomic_write(path, content, mode)
    if type(content) ~= "string" then
        return nil, "atomic write content must be a string"
    end

    local suffix = string.format(
        "%s.%s.%s",
        tostring(ngx.worker.pid()),
        tostring(math.floor(ngx.now() * 1000000)),
        tostring(next_sequence())
    )
    local temp_path = path .. ".tmp." .. suffix
    local flags = bit.bor(O_WRONLY, O_CREAT, O_EXCL, O_NOFOLLOW, O_CLOEXEC)
    local target_mode = mode or DEFAULT_MODE
    local open_mode = ffi.new("unsigned int", target_mode)
    local fd = ffi.C.open(temp_path, flags, open_mode)
    if fd < 0 then
        return nil,
            "failed to create temporary Authelia file "
            .. temp_path
            .. " errno="
            .. tostring(ffi.errno())
    end

    local written, write_err = write_all(fd, content)
    if not written then
        close_fd(fd)
        os.remove(temp_path)
        return nil, write_err
    end

    if ffi.C.fchmod(fd, target_mode) ~= 0 then
        local errno = ffi.errno()
        close_fd(fd)
        os.remove(temp_path)
        return nil,
            "failed to chmod temporary Authelia file errno=" .. tostring(errno)
    end

    -- fsync antes do rename garante que o snapshot novo ja esteja persistido.
    if ffi.C.fsync(fd) ~= 0 then
        local errno = ffi.errno()
        close_fd(fd)
        os.remove(temp_path)
        return nil,
            "failed to fsync temporary Authelia file errno=" .. tostring(errno)
    end
    close_fd(fd)

    -- Temp e destino ficam no mesmo diretorio/volume; rename troca o snapshot
    -- de forma atomica para leitores (Authelia e init_worker).
    local renamed, rename_err = os.rename(temp_path, path)
    if not renamed then
        os.remove(temp_path)
        return nil, rename_err or "failed to atomically replace Authelia file"
    end

    -- Persistir a entrada de diretorio fecha a janela em que o conteudo ja foi
    -- fsyncado, mas o rename poderia se perder num crash do host. Se esse fsync
    -- falhar, o arquivo novo ja esta visivel; nao reportamos a mutacao como
    -- inexistente para evitar que o caller tome decisoes com um estado falso.
    local directory_synced, directory_err = fsync_parent_directory(path)
    if not directory_synced then
        ngx.log(
            ngx.CRIT,
            "[AUTHELIA-STORE] atomic rename completed but parent fsync failed: ",
            tostring(directory_err)
        )
        return true, directory_err
    end

    return true
end

return M
