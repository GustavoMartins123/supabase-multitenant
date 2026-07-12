local cjson = require("cjson.safe")
local lyaml = require("lyaml")
local user_identity = require("project_context.user_identity")
local authelia_identifiers = require("admin_api.authelia_identifiers")

local M = {}

local YAML_PATH = "/config/users_database.yml"
local LOCK_KEY = "user-profile:yaml-write"
local lock_dict = ngx.shared.service_keys

local field_limits = {
    display_name = 120,
    given_name = 120,
    family_name = 120,
    middle_name = 120,
    nickname = 120,
    gender = 50,
    birthdate = 10,
    website = 500,
    profile = 500,
    zoneinfo = 100,
    locale = 35,
    phone_number = 50,
    phone_extension = 20,
    street_address = 250,
    locality = 120,
    region = 120,
    postal_code = 40,
    country = 120,
}

local yaml_fields = {
    display_name = "displayname",
    given_name = "given_name",
    family_name = "family_name",
    middle_name = "middle_name",
    nickname = "nickname",
    gender = "gender",
    birthdate = "birthdate",
    website = "website",
    profile = "profile",
    zoneinfo = "zoneinfo",
    locale = "locale",
    phone_number = "phone_number",
    phone_extension = "phone_extension",
}

local address_fields = {
    "street_address",
    "locality",
    "region",
    "postal_code",
    "country",
}

local function trim(value)
    if value == nil or value == cjson.null then
        return ""
    end
    return tostring(value):gsub("^%s+", ""):gsub("%s+$", "")
end

local function read_file(path)
    local handle, err = io.open(path, "rb")
    if not handle then
        return nil, err
    end
    local content = handle:read("*a")
    handle:close()
    return content
end

local function write_raw(content)
    local suffix = string.format("%s.%s", ngx.worker.pid(), math.floor(ngx.now() * 1000000))
    local temp_path = YAML_PATH .. ".tmp." .. suffix
    local handle, err = io.open(temp_path, "wb")
    if not handle then
        return nil, err
    end
    local ok, write_err = handle:write(content)
    handle:close()
    if not ok then
        os.remove(temp_path)
        return nil, write_err
    end
    local renamed, rename_err = os.rename(temp_path, YAML_PATH)
    if not renamed then
        os.remove(temp_path)
        return nil, rename_err
    end
    return true
end

local function write_data(data)
    local serialized, err = lyaml.dump({ data })
    if not serialized then
        return nil, err or "failed to serialize users database"
    end
    return write_raw(serialized)
end

local function load_data()
    local content, read_err = read_file(YAML_PATH)
    if not content then
        return nil, nil, read_err
    end
    local ok, data = pcall(lyaml.load, content)
    if not ok or type(data) ~= "table" then
        return nil, nil, "invalid users database"
    end
    data.users = data.users or {}
    return data, content
end

local function acquire_lock()
    if not lock_dict then
        return "unlocked"
    end
    local token = string.format("%s:%s", ngx.worker.pid(), math.floor(ngx.now() * 1000000))
    for _ = 1, 100 do
        if lock_dict:add(LOCK_KEY, token, 8) then
            return token
        end
        ngx.sleep(0.02)
    end
    return nil, "profile store is busy"
end

local function release_lock(token)
    if not lock_dict or token == "unlocked" then
        return
    end
    if lock_dict:get(LOCK_KEY) == token then
        lock_dict:delete(LOCK_KEY)
    end
end

local function find_user(data, email)
    local normalized = user_identity.normalize_email(email or "")
    if normalized == "" then
        return nil, nil, "authenticated email is missing"
    end
    for username, user in pairs(data.users or {}) do
        if type(user) == "table" and user_identity.normalize_email(user.email or "") == normalized then
            return username, user
        end
    end
    return nil, nil, "user not found in Authelia database"
end

local function resolve_user_id(username, email)
    local normalized = user_identity.normalize_email(email or "")
    local cache = ngx.shared.users_cache
    local cached = cache and cache:get("email:" .. normalized)
    if cached and cached ~= "" then
        return cached
    end
    local generated, _, err = authelia_identifiers.ensure_identifier(username)
    if not generated then
        return nil, err or "opaque identifier unavailable"
    end
    return generated
end

local function group_state(groups)
    local active = false
    local admin = false
    for _, group in ipairs(groups or {}) do
        if group == "active" then
            active = true
        elseif group == "admin" then
            admin = true
        end
    end
    return active, admin
end

local function profile_from_user(username, user_id, user)
    local active_group, admin = group_state(user.groups)
    local address = type(user.address) == "table" and user.address or {}
    local profile = {
        user_id = user_id,
        username = username,
        email = trim(user.email),
        display_name = trim(user.displayname),
        given_name = trim(user.given_name),
        family_name = trim(user.family_name),
        middle_name = trim(user.middle_name),
        nickname = trim(user.nickname),
        picture = trim(user.picture),
        website = trim(user.website),
        profile = trim(user.profile),
        gender = trim(user.gender),
        birthdate = trim(user.birthdate),
        zoneinfo = trim(user.zoneinfo),
        locale = trim(user.locale),
        phone_number = trim(user.phone_number),
        phone_extension = trim(user.phone_extension),
        street_address = trim(address.street_address),
        locality = trim(address.locality),
        region = trim(address.region),
        postal_code = trim(address.postal_code),
        country = trim(address.country),
        groups = user.groups or {},
        is_active = user.disabled ~= true and active_group,
        is_admin = admin,
        created_at = trim(type(user.extra) == "table" and user.extra.created_at or ""),
    }
    if profile.display_name == "" then
        profile.display_name = username
    end
    return profile
end

local function cache_profile(profile)
    local cache = ngx.shared.users_cache
    if not cache or not profile.user_id or profile.user_id == "" then
        return
    end
    local normalized_email = user_identity.normalize_email(profile.email)
    local payload = {
        username = profile.username,
        display_name = profile.display_name,
        email = normalized_email,
        user_uuid = profile.user_id,
        is_active = profile.is_active,
        is_admin = profile.is_admin,
        profile = profile,
    }
    local encoded = cjson.encode(payload)
    if encoded then
        cache:set(profile.user_id, encoded)
        if normalized_email ~= "" then
            cache:set("email:" .. normalized_email, profile.user_id)
        end
    end
end

local function validate_url(value, field)
    if value == "" then
        return true
    end
    local _, rest = value:match("^(https?)://(.+)$")
    if not rest or rest:find("%s") then
        return nil, field .. " must use an absolute http or https URL"
    end
    local authority = rest:match("^([^/%?#]+)")
    if not authority or authority == "" or authority:find("@", 1, true) then
        return nil, field .. " must use an absolute http or https URL"
    end
    return true
end

local function validate_locale(value)
    if value == "" then
        return true
    end
    if value:sub(1, 1) == "-" or value:sub(-1) == "-" or value:find("--", 1, true) then
        return false
    end
    local index = 0
    for part in value:gmatch("[^%-]+") do
        index = index + 1
        if index == 1 then
            if #part < 2 or #part > 3 or not part:match("^%a+$") then
                return false
            end
        elseif #part < 2 or #part > 8 or not part:match("^%w+$") then
            return false
        end
    end
    return index > 0
end

local function validate_payload(payload)
    if type(payload) ~= "table" then
        return nil, "invalid profile payload"
    end
    if payload.username ~= nil or payload.email ~= nil or payload.picture ~= nil then
        return nil, "username, email and picture are immutable in this endpoint"
    end
    local normalized = {}
    for field, limit in pairs(field_limits) do
        if payload[field] ~= nil then
            local value = trim(payload[field])
            if #value > limit then
                return nil, field .. " exceeds the maximum length"
            end
            normalized[field] = value
        end
    end
    if normalized.display_name ~= nil and normalized.display_name == "" then
        return nil, "display_name is required"
    end
    local ok, err = validate_url(normalized.website or "", "website")
    if not ok then
        return nil, err
    end
    ok, err = validate_url(normalized.profile or "", "profile")
    if not ok then
        return nil, err
    end
    if normalized.birthdate and normalized.birthdate ~= "" and not normalized.birthdate:match("^%d%d%d%d%-%d%d%-%d%d$") then
        return nil, "birthdate must use YYYY-MM-DD"
    end
    if normalized.locale and not validate_locale(normalized.locale) then
        return nil, "locale is invalid"
    end
    if normalized.zoneinfo and normalized.zoneinfo ~= "" and not normalized.zoneinfo:match("^[%w%+%-%._/]+$") then
        return nil, "zoneinfo is invalid"
    end
    return normalized
end

local function mutate(email, apply, syncer)
    local token, lock_err = acquire_lock()
    if not token then
        return nil, lock_err
    end

    local data, original, load_err = load_data()
    if not data then
        release_lock(token)
        return nil, load_err
    end

    local username, user, find_err = find_user(data, email)
    if not user then
        release_lock(token)
        return nil, find_err
    end

    local user_id, id_err = resolve_user_id(username, user.email)
    if not user_id then
        release_lock(token)
        return nil, id_err
    end

    local applied, apply_err = apply(user)
    if not applied then
        release_lock(token)
        return nil, apply_err
    end

    local profile = profile_from_user(username, user_id, user)
    local written, write_err = write_data(data)
    if not written then
        release_lock(token)
        return nil, write_err
    end

    if syncer then
        local synced, sync_err = syncer(profile)
        if not synced then
            local restored, restore_err = write_raw(original)
            release_lock(token)
            return nil, "profile synchronization failed: " .. tostring(sync_err or restore_err or "unknown error")
        end
    end

    cache_profile(profile)
    release_lock(token)
    return profile
end

function M.get(email)
    local data, _, load_err = load_data()
    if not data then
        return nil, load_err
    end
    local username, user, find_err = find_user(data, email)
    if not user then
        return nil, find_err
    end
    local user_id, id_err = resolve_user_id(username, user.email)
    if not user_id then
        return nil, id_err
    end
    local profile = profile_from_user(username, user_id, user)
    cache_profile(profile)
    return profile
end

function M.update(email, payload, syncer)
    local normalized, validation_err = validate_payload(payload)
    if not normalized then
        return nil, validation_err
    end
    return mutate(email, function(user)
        for field, yaml_field in pairs(yaml_fields) do
            if normalized[field] ~= nil then
                user[yaml_field] = normalized[field]
            end
        end

        local address_changed = false
        local address = type(user.address) == "table" and user.address or {}
        for _, field in ipairs(address_fields) do
            if normalized[field] ~= nil then
                address[field] = normalized[field]
                address_changed = true
            end
        end
        if address_changed then
            local has_value = false
            for _, field in ipairs(address_fields) do
                if trim(address[field]) ~= "" then
                    has_value = true
                    break
                end
            end
            user.address = has_value and address or lyaml.null
        end

        return true
    end, syncer)
end

function M.set_picture(email, picture, syncer)
    local value = trim(picture)
    local ok, err = validate_url(value, "picture")
    if not ok then
        return nil, err
    end
    return mutate(email, function(user)
        user.picture = value
        return true
    end, syncer)
end

function M.cache(profile)
    cache_profile(profile)
end

return M
