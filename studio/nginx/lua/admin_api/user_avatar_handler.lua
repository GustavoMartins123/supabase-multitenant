local cjson = require("cjson.safe")
local lfs = require("lfs")
local store = require("admin_api.user_profile_store")
local user_sync = require("admin_api.user_sync")

local M = {}

local AVATAR_DIR = "/config/profile-pictures"
local MAX_BYTES = 2 * 1024 * 1024

local function respond_json(status, payload)
    ngx.status = status
    ngx.header.content_type = "application/json; charset=utf-8"
    ngx.say(cjson.encode(payload))
    return ngx.exit(status)
end

local function sync_profile(profile)
    return user_sync.sync_user({
        id = profile.user_id,
        username = profile.username,
        display_name = profile.display_name,
        groups = profile.groups,
        is_active = profile.is_active,
        source = {
            name = "studio_profile",
            email = profile.email,
            profile = profile,
        },
    })
end

local function avatar_path(user_id)
    if not tostring(user_id or ""):match("^[0-9a-fA-F%-]+$") then
        return nil
    end
    return AVATAR_DIR .. "/" .. user_id .. ".avatar"
end

local function detect_type(data)
    if #data >= 8 and data:sub(1, 8) == "\137PNG\r\n\26\n" then
        return "image/png"
    end
    if #data >= 3 and string.byte(data, 1) == 255 and string.byte(data, 2) == 216 and string.byte(data, 3) == 255 then
        return "image/jpeg"
    end
    if #data >= 12 and data:sub(1, 4) == "RIFF" and data:sub(9, 12) == "WEBP" then
        return "image/webp"
    end
    return nil
end

local function read_upload()
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
            local attributes = lfs.attributes(body_file)
            if attributes and attributes.size and attributes.size > MAX_BYTES then
                return nil, "avatar exceeds 2 MB"
            end
            local file, err = io.open(body_file, "rb")
            if not file then
                return nil, err
            end
            data = file:read(MAX_BYTES + 1)
            file:close()
        end
    end
    if not data or data == "" then
        return nil, "avatar body is required"
    end
    if #data > MAX_BYTES then
        return nil, "avatar exceeds 2 MB"
    end
    local mime = detect_type(data)
    if not mime then
        return nil, "only PNG, JPEG and WebP are accepted"
    end
    return data, mime
end

local function ensure_directory()
    local mode = lfs.attributes(AVATAR_DIR, "mode")
    if mode == "directory" then
        return true
    end
    local ok, err = lfs.mkdir(AVATAR_DIR)
    if not ok and lfs.attributes(AVATAR_DIR, "mode") ~= "directory" then
        return nil, err
    end
    return true
end

local function get_profile(email)
    local profile, err = store.get(email)
    if not profile then
        return nil, err
    end
    local path = avatar_path(profile.user_id)
    if not path then
        return nil, "invalid user identifier"
    end
    return profile, path
end

local function serve(path)
    local file = io.open(path, "rb")
    if not file then
        return respond_json(404, { error = "avatar not found" })
    end
    local data = file:read("*a")
    file:close()
    local mime = detect_type(data or "")
    if not mime then
        return respond_json(415, { error = "stored avatar is invalid" })
    end
    local attributes = lfs.attributes(path) or {}
    local etag = string.format('"%s-%s"', tostring(attributes.modification or 0), tostring(attributes.size or #data))
    ngx.header["ETag"] = etag
    ngx.header["Cache-Control"] = "private, max-age=3600"
    if ngx.var.http_if_none_match == etag then
        ngx.status = 304
        return ngx.exit(304)
    end
    ngx.header.content_type = mime
    ngx.header["X-Content-Type-Options"] = "nosniff"
    ngx.print(data)
    return ngx.exit(200)
end

local function upload(email, profile, path)
    local data, upload_err = read_upload()
    if not data then
        return respond_json(400, { error = upload_err })
    end
    local ready, directory_err = ensure_directory()
    if not ready then
        return respond_json(500, { error = directory_err or "avatar directory unavailable" })
    end
    local suffix = string.format("%s.%s", ngx.worker.pid(), math.floor(ngx.now() * 1000000))
    local temp_path = path .. ".tmp." .. suffix
    local backup_path = path .. ".bak." .. suffix
    local file, open_err = io.open(temp_path, "wb")
    if not file then
        return respond_json(500, { error = open_err or "failed to create avatar" })
    end
    local written, write_err = file:write(data)
    file:close()
    if not written then
        os.remove(temp_path)
        return respond_json(500, { error = write_err or "failed to write avatar" })
    end
    local had_previous = lfs.attributes(path, "mode") == "file"
    if had_previous then
        local backed, backup_err = os.rename(path, backup_path)
        if not backed then
            os.remove(temp_path)
            return respond_json(500, { error = backup_err or "failed to preserve previous avatar" })
        end
    end
    local installed, install_err = os.rename(temp_path, path)
    if not installed then
        if had_previous then
            os.rename(backup_path, path)
        end
        os.remove(temp_path)
        return respond_json(500, { error = install_err or "failed to install avatar" })
    end
    local origin = ngx.var.studio_public_origin or (ngx.var.scheme .. "://" .. ngx.var.http_host)
    local picture = origin
        .. "/api/user/me/avatar/"
        .. profile.user_id
        .. "?v="
        .. tostring(math.floor(ngx.now() * 1000))
    local updated, update_err = store.set_picture(email, picture, sync_profile)
    if not updated then
        os.remove(path)
        if had_previous then
            os.rename(backup_path, path)
        end
        return respond_json(502, { error = update_err or "failed to update avatar profile" })
    end
    if had_previous then
        os.remove(backup_path)
    end
    return respond_json(200, updated)
end

local function remove_avatar(email, path)
    local updated, update_err = store.set_picture(email, "", sync_profile)
    if not updated then
        return respond_json(502, { error = update_err or "failed to remove avatar profile" })
    end
    os.remove(path)
    return respond_json(200, updated)
end

function M.handle()
    local email = ngx.var.authelia_email or ""
    if email == "" then
        return respond_json(401, { error = "authenticated email is missing" })
    end
    local profile, path_or_err = get_profile(email)
    if not profile then
        return respond_json(500, { error = path_or_err or "failed to load profile" })
    end
    local method = ngx.req.get_method()
    local uri = ngx.var.uri or ""
    local requested_user_id = uri:match("^/api/user/me/avatar/([0-9a-fA-F%-]+)$")
    if method == "GET" then
        local requested_path = path_or_err
        if requested_user_id then
            requested_path = avatar_path(requested_user_id)
            if not requested_path then
                return respond_json(400, { error = "invalid user identifier" })
            end
        end
        return serve(requested_path)
    end
    if uri ~= "/api/user/me/avatar" then
        return respond_json(405, { error = "method not allowed" })
    end
    if method == "PUT" then
        return upload(email, profile, path_or_err)
    end
    if method == "DELETE" then
        return remove_avatar(email, path_or_err)
    end
    return respond_json(405, { error = "method not allowed" })
end

return M
