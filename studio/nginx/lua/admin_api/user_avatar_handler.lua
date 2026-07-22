local cjson = require("cjson.safe")
local lfs = require("lfs")
local processor = require("admin_api.avatar_processor")
local store = require("admin_api.user_profile_store")
local user_sync = require("admin_api.user_sync")

local M = {}

local AVATAR_DIR = "/config/profile-pictures"

local function respond_json(status, payload)
    ngx.status = status
    ngx.header.content_type = "application/json; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"
    if status == ngx.HTTP_SERVICE_UNAVAILABLE then
        ngx.header["Retry-After"] = "1"
    end
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
    return processor.avatar_path(AVATAR_DIR, user_id)
end

local function marker_path(path)
    return processor.marker_path(path)
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
    if lfs.attributes(path, "mode") ~= "file" then
        return respond_json(404, { error = "avatar not found" })
    end
    if lfs.attributes(marker_path(path), "mode") ~= "file" then
        return respond_json(415, { error = "stored avatar is not normalized" })
    end
    local data, read_err = processor.read_limited_file(path)
    if not data then
        return respond_json(415, { error = read_err or "stored avatar is invalid" })
    end
    if processor.detect_type(data) ~= "image/webp" then
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
    ngx.status = ngx.HTTP_OK
    ngx.header.content_type = "image/webp"
    ngx.header["Content-Length"] = #data
    ngx.header["X-Content-Type-Options"] = "nosniff"
    ngx.print(data)
    return
end

local function upload(email, profile, path)
    local data, upload_err = processor.read_upload()
    if not data then
        return respond_json(400, { error = upload_err })
    end
    local normalized, normalize_err, normalize_status = processor.normalize_image(data)
    if not normalized then
        return respond_json(normalize_status or 422, { error = normalize_err or "avatar is invalid" })
    end
    data = normalized
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
    local had_previous_marker = lfs.attributes(marker_path(path), "mode") == "file"
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
    local marked, marker_err = processor.write_marker(path)
    if not marked then
        os.remove(path)
        os.remove(marker_path(path))
        if had_previous then
            os.rename(backup_path, path)
            if had_previous_marker then
                processor.write_marker(path)
            end
        end
        return respond_json(500, { error = marker_err or "failed to finalize avatar" })
    end
    local canonical_id = processor.normalize_uuid(profile.user_id)
    local origin = ngx.var.studio_public_origin or (ngx.var.scheme .. "://" .. ngx.var.http_host)
    local picture = origin
        .. "/api/users/"
        .. canonical_id
        .. "/avatar?v="
        .. tostring(math.floor(ngx.now() * 1000))
    local updated, update_err = store.set_picture(email, picture, sync_profile)
    if not updated then
        os.remove(path)
        os.remove(marker_path(path))
        if had_previous then
            os.rename(backup_path, path)
            if had_previous_marker then
                processor.write_marker(path)
            end
        end
        return respond_json(502, { error = update_err or "failed to update avatar profile" })
    end
    if had_previous then
        os.remove(backup_path)
    end
    return respond_json(200, updated)
end

local function remove_avatar(email, path)
    local suffix = string.format("%s.%s", ngx.worker.pid(), math.floor(ngx.now() * 1000000))
    local backup_path = path .. ".delete." .. suffix
    local backup_marker = marker_path(path) .. ".delete." .. suffix
    local had_avatar = lfs.attributes(path, "mode") == "file"
    local had_marker = lfs.attributes(marker_path(path), "mode") == "file"
    if had_avatar then
        local moved, move_err = os.rename(path, backup_path)
        if not moved then
            return respond_json(500, { error = move_err or "failed to stage avatar removal" })
        end
    end
    if had_marker then
        local moved, move_err = os.rename(marker_path(path), backup_marker)
        if not moved then
            if had_avatar then
                os.rename(backup_path, path)
            end
            return respond_json(500, { error = move_err or "failed to stage avatar metadata removal" })
        end
    end
    local updated, update_err = store.set_picture(email, "", sync_profile)
    if not updated then
        if had_avatar then
            os.rename(backup_path, path)
        end
        if had_marker then
            os.rename(backup_marker, marker_path(path))
        end
        return respond_json(502, { error = update_err or "failed to remove avatar profile" })
    end
    if had_avatar then
        os.remove(backup_path)
    end
    if had_marker then
        os.remove(backup_marker)
    end
    return respond_json(200, updated)
end

local function requested_avatar_path(user_id)
    local canonical = processor.normalize_uuid(user_id)
    if not canonical then
        return nil, "invalid"
    end
    local cache = ngx.shared.users_cache
    local encoded = cache and cache:get(canonical)
    local target = encoded and cjson.decode(encoded)
    if not target or target.is_active ~= true or target.user_uuid ~= canonical then
        return nil, "not_found"
    end
    return avatar_path(canonical)
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
    if profile.is_active ~= true then
        return respond_json(403, { error = "active profile is required" })
    end

    local method = ngx.req.get_method()
    local uri = ngx.var.uri or ""
    local requested_user_id = uri:match("^/api/users/([^/]+)/avatar$")
    if method == "GET" then
        if not requested_user_id then
            return respond_json(405, { error = "method not allowed" })
        end
        local requested_path, requested_err = requested_avatar_path(requested_user_id)
        if requested_err == "invalid" then
            return respond_json(400, { error = "invalid user identifier" })
        end
        if not requested_path then
            return respond_json(404, { error = "avatar not found" })
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
