local pipe = require("ngx.pipe")

local M = {}

local TEMP_DIR = "/tmp"
local MAX_BYTES = 2 * 1024 * 1024
local UUID_PATTERN = "^[0-9a-fA-F]{8}%-[0-9a-fA-F]{4}%-[0-9a-fA-F]{4}%-[0-9a-fA-F]{4}%-[0-9a-fA-F]{12}$"

local function bounded_integer(name, default, minimum, maximum)
    local value = tonumber(os.getenv(name) or "") or default
    value = math.floor(value)
    if value < minimum then
        return minimum
    end
    if value > maximum then
        return maximum
    end
    return value
end

local MAX_PROCESS_CONCURRENCY = bounded_integer("AVATAR_PROCESS_MAX_CONCURRENCY", 2, 1, 16)
local PROCESS_TIMEOUT_MS = bounded_integer("AVATAR_PROCESS_TIMEOUT_MS", 15000, 1000, 60000)
local MAX_PIXELS = bounded_integer("AVATAR_MAX_PIXELS", 16000000, 1000000, 64000000)
local MAX_SOURCE_EDGE = bounded_integer("AVATAR_MAX_SOURCE_EDGE", 8192, 512, 32768)
local MAX_EDGE = bounded_integer("AVATAR_MAX_EDGE", 512, 64, 2048)
local VIPS_CONCURRENCY = bounded_integer("VIPS_CONCURRENCY", 1, 1, 4)

function M.normalize_uuid(user_id)
    local value = tostring(user_id or "")
    if not value:match(UUID_PATTERN) then
        return nil
    end
    return value:lower()
end

function M.avatar_path(avatar_dir, user_id)
    local canonical = M.normalize_uuid(user_id)
    if not canonical then
        return nil
    end
    return avatar_dir .. "/" .. canonical .. ".avatar"
end

function M.marker_path(path)
    return path .. ".normalized-v2"
end

function M.detect_type(data)
    if #data >= 8 and data:sub(1, 8) == "\137PNG\r\n\26\n" then
        return "image/png"
    end
    if #data >= 3
        and string.byte(data, 1) == 255
        and string.byte(data, 2) == 216
        and string.byte(data, 3) == 255
    then
        return "image/jpeg"
    end
    if #data >= 12 and data:sub(1, 4) == "RIFF" and data:sub(9, 12) == "WEBP" then
        return "image/webp"
    end
    return nil
end

function M.read_limited_file(path)
    local file, open_err = io.open(path, "rb")
    if not file then
        return nil, open_err
    end
    local data = file:read(MAX_BYTES + 1)
    file:close()
    if not data or data == "" then
        return nil, "empty file"
    end
    if #data > MAX_BYTES then
        return nil, "file exceeds 2 MB"
    end
    return data
end

function M.read_upload()
    local declared = tonumber(ngx.var.content_length or "0") or 0
    if declared <= 0 then
        return nil, "Content-Length is required"
    end
    if declared > MAX_BYTES then
        return nil, "avatar exceeds 2 MB"
    end
    ngx.req.read_body()
    local data = ngx.req.get_body_data()
    if not data then
        local body_file = ngx.req.get_body_file()
        if body_file then
            data = M.read_limited_file(body_file)
        end
    end
    if not data or data == "" then
        return nil, "avatar body is required"
    end
    if #data > MAX_BYTES then
        return nil, "avatar exceeds 2 MB"
    end
    if not M.detect_type(data) then
        return nil, "only PNG, JPEG and WebP are accepted"
    end
    return data
end

local function temp_paths()
    local suffix = string.format(
        "%s-%s-%s",
        ngx.worker.pid(),
        ngx.var.connection or "0",
        math.floor(ngx.now() * 1000000)
    )
    return TEMP_DIR .. "/avatar-" .. suffix .. ".input",
        TEMP_DIR .. "/avatar-" .. suffix .. ".webp"
end

local function run_process(args)
    local proc, spawn_err = pipe.spawn(args, {
        merge_stderr = true,
        buffer_size = 16384,
        stdout_read_timeout = PROCESS_TIMEOUT_MS,
        wait_timeout = PROCESS_TIMEOUT_MS,
        environ = {
            "VIPS_CONCURRENCY=" .. tostring(VIPS_CONCURRENCY),
            "VIPS_DISC_THRESHOLD=20m",
            "TMPDIR=" .. TEMP_DIR,
        },
    })
    if not proc then
        ngx.log(ngx.ERR, "failed to spawn avatar image process: ", spawn_err or "unknown error")
        return nil, "unavailable"
    end

    local output, read_err, partial = proc:stdout_read_all()
    if not output and read_err == "closed" then
        output = partial or ""
    elseif not output then
        proc:kill(9)
        proc:wait()
        ngx.log(ngx.ERR, "avatar image process output failed: ", read_err or "unknown error")
        return nil, read_err == "timeout" and "timeout" or "unavailable"
    end

    local waited, reason, status = proc:wait()
    if waited ~= true then
        ngx.log(
            ngx.WARN,
            "avatar image process rejected input: reason=",
            reason or "unknown",
            " status=",
            tostring(status or "")
        )
        return nil, reason == "timeout" and "timeout" or "exit"
    end
    return output or ""
end

local function image_field(input_path, field)
    local output, process_err = run_process({
        "/usr/bin/vipsheader",
        "-f",
        field,
        input_path,
    })
    if not output then
        return nil, process_err
    end
    return tonumber(output:match("^%s*(%d+)"))
end

local function normalize_image_unlocked(data)
    local input_path, output_path = temp_paths()
    local input, open_err = io.open(input_path, "wb")
    if not input then
        return nil, open_err or "temporary file unavailable", 500
    end
    local written, write_err = input:write(data)
    input:close()
    if not written then
        os.remove(input_path)
        return nil, write_err or "temporary file write failed", 500
    end

    local width, width_err = image_field(input_path, "width")
    local height, height_err = image_field(input_path, "height")
    if not width or not height then
        os.remove(input_path)
        if width_err == "timeout" or height_err == "timeout" then
            return nil, "image processing timed out", 503
        end
        if width_err == "unavailable" or height_err == "unavailable" then
            return nil, "image decoder unavailable", 500
        end
        return nil, "avatar is corrupt or unsupported", 422
    end
    if width <= 0 or height <= 0 or width > MAX_SOURCE_EDGE or height > MAX_SOURCE_EDGE
        or width * height > MAX_PIXELS
    then
        os.remove(input_path)
        return nil, "avatar dimensions are invalid or too large", 422
    end

    local pages, pages_err = image_field(input_path, "n-pages")
    if pages and pages > 1 then
        os.remove(input_path)
        return nil, "animated avatars are not accepted", 422
    end
    if not pages and pages_err ~= "exit" then
        os.remove(input_path)
        if pages_err == "timeout" then
            return nil, "image processing timed out", 503
        end
        return nil, "image decoder unavailable", 500
    end

    local _, thumbnail_err = run_process({
        "/usr/bin/vipsthumbnail",
        input_path,
        "--size=" .. tostring(MAX_EDGE) .. "x" .. tostring(MAX_EDGE) .. ">",
        "--rotate",
        "--delete",
        "-o",
        output_path .. "[Q=85,strip]",
    })
    os.remove(input_path)
    if thumbnail_err then
        os.remove(output_path)
        if thumbnail_err == "timeout" then
            return nil, "image processing timed out", 503
        end
        if thumbnail_err == "unavailable" then
            return nil, "image decoder unavailable", 500
        end
        return nil, "avatar is corrupt or unsupported", 422
    end

    local normalized, output_err = M.read_limited_file(output_path)
    os.remove(output_path)
    if not normalized then
        return nil, output_err or "normalized avatar is invalid", 422
    end
    if M.detect_type(normalized) ~= "image/webp" then
        return nil, "normalized avatar is invalid", 422
    end
    return normalized
end

function M.normalize_image(data)
    local processing = ngx.shared.avatar_processing
    if not processing then
        return nil, "avatar processing capacity is unavailable", 503
    end
    local token = string.format(
        "%s:%s:%s",
        ngx.worker.pid(),
        ngx.var.connection or "0",
        math.floor(ngx.now() * 1000000)
    )
    local slot_key
    for slot = 1, MAX_PROCESS_CONCURRENCY do
        local candidate = "slot:" .. tostring(slot)
        local acquired, acquire_err = processing:add(
            candidate,
            token,
            math.ceil(PROCESS_TIMEOUT_MS / 1000) + 5
        )
        if acquired then
            slot_key = candidate
            break
        end
        if acquire_err ~= "exists" then
            ngx.log(
                ngx.ERR,
                "failed to reserve avatar processing slot: ",
                acquire_err or "unknown error"
            )
            return nil, "avatar processing capacity is unavailable", 503
        end
    end
    if not slot_key then
        return nil, "avatar processing is busy", 503
    end

    local called, normalized, normalize_err, status = pcall(normalize_image_unlocked, data)
    if processing:get(slot_key) == token then
        processing:delete(slot_key)
    end
    if not called then
        ngx.log(ngx.ERR, "unexpected avatar processing failure: ", normalized)
        return nil, "avatar processing failed", 500
    end
    return normalized, normalize_err, status
end

function M.write_marker(path)
    local marker = M.marker_path(path)
    local file, err = io.open(marker, "wb")
    if not file then
        return nil, err
    end
    local ok, write_err = file:write("webp-512-metadata-free-v2\n")
    file:close()
    if not ok then
        os.remove(marker)
        return nil, write_err
    end
    return true
end

return M
