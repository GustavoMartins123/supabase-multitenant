local cjson = require("cjson.safe")
local store = require("admin_api.authelia_user_store")
local files = require("admin_api.authelia_file_store")
local identifiers = require("admin_api.authelia_identifiers")
local hmac = require("security.internal_hmac")
local admin_groups = require("security.admin_groups")
local identity = require("project_context.user_identity")
local M = {}
local sequence_path = "/config/.studio-directory-sequence"
local SEQUENCE_MODE = 384 -- 0600
local profile_fields = {"given_name", "family_name", "middle_name", "nickname", "picture", "website", "profile", "gender", "birthdate", "zoneinfo", "locale", "phone_number", "phone_extension"}
local address_fields = {"street_address", "locality", "region", "postal_code", "country"}

local cached_users_raw = nil
local cached_ids_raw = nil
local cached_snapshot = nil
local cached_by_email = nil
local cached_usernames = nil
local cached_user_ids = nil

local function user_ids_match(left, right)
    if type(left) ~= "table" or type(right) ~= "table" then
        return false
    end
    for key, value in pairs(left) do
        if right[key] ~= value then
            return false
        end
    end
    for key, value in pairs(right) do
        if left[key] ~= value then
            return false
        end
    end
    return true
end

local function load_snapshot_locked()
    local raw = type(store.read_raw) == "function" and store.read_raw() or nil
    if raw and cached_snapshot and cached_users_raw == raw and cached_usernames and cached_user_ids then
        local current_ids, _, id_err = identifiers.ensure_identifiers(cached_usernames)
        if not current_ids then
            return nil, id_err
        end
        if user_ids_match(current_ids, cached_user_ids) then
            return cached_snapshot
        end
    end

    local data, loaded_raw, err = store.load()
    if not data then return nil, err end
    local revision, hash_err = hmac.sha256_hex(loaded_raw)
    if not revision then return nil, hash_err end
    assert(cjson.array_mt, "cjson array metatable is required")
    local users = setmetatable({}, cjson.array_mt)
    local seen_email = {}
    local by_email = {}
    local usernames = {}
    for username in pairs(data.users) do
        if username ~= "__bootstrap_placeholder__" then usernames[#usernames + 1] = username end
    end
    table.sort(usernames)
    local user_ids, _, id_err = identifiers.ensure_identifiers(usernames)
    if not user_ids then return nil, id_err end
    for username, attr in pairs(data.users) do
        if username ~= "__bootstrap_placeholder__" then
            if type(attr) ~= "table" or (attr.groups ~= nil and type(attr.groups) ~= "table") then return nil, "invalid directory user" end
            -- No groups is an explicit denial of all grants, never an active user.
            local groups = admin_groups.parse(table.concat(attr.groups or {}, ","))
            if not groups then return nil, "invalid directory groups" end
            setmetatable(groups, cjson.array_mt)
            local user_id = user_ids[username]
            if not user_id then return nil, "canonical user identifier absent" end
            local active = false
            for _, group in ipairs(groups) do if group == "active" then active = true end end
            local email = identity.normalize_email(attr.email or "")
            if email ~= "" and seen_email[email] then return nil, "duplicate directory email" end
            seen_email[email] = true
            local profile = {display_name=attr.displayname or username}
            for _, field in ipairs(profile_fields) do profile[field] = attr[field] or "" end
            for _, field in ipairs(address_fields) do profile[field] = type(attr.address)=="table" and attr.address[field] or "" end
            local entry = {
                id=user_id, username=username, display_name=attr.displayname or username,
                groups=groups, is_active=active and attr.disabled ~= true,
                source={name="studio_directory", email=email, profile=profile},
            }
            users[#users+1] = entry
            if email ~= "" then
                by_email[email] = entry
            end
        end
    end
    table.sort(users, function(a,b) return a.username < b.username end)
    local snapshot = {revision=revision, users=users}
    cached_users_raw = loaded_raw
    cached_ids_raw = type(identifiers.raw_state) == "function" and identifiers.raw_state() or nil
    cached_snapshot = snapshot
    cached_by_email = by_email
    cached_usernames = usernames
    cached_user_ids = user_ids
    return snapshot
end

-- Caller must hold users_database.yml's lock. This is the only snapshot source.
function M.read_locked(assign_sequence)
    local base_snapshot, err = load_snapshot_locked()
    if not base_snapshot then return nil, err end
    if assign_sequence then
        local file = io.open(sequence_path, "rb")
        if not file then return nil, "directory sequence unavailable; run installation configuration" end
        local raw_sequence = file:read("*a")
        file:close()
        local sequence = tonumber(raw_sequence)
        if not sequence or sequence < 0 or sequence % 1 ~= 0 or sequence >= 9007199254740991 then return nil, "invalid directory sequence" end
        sequence = sequence + 1
        local written, write_err = files.atomic_write(sequence_path, tostring(sequence), SEQUENCE_MODE)
        if not written then return nil, write_err end
        return {revision=base_snapshot.revision, users=base_snapshot.users, sequence=sequence}
    end
    return base_snapshot
end

function M.for_email(email)
    local normalized = identity.normalize_email(email)
    if cached_snapshot and cached_by_email
        and type(store.read_raw) == "function"
        and type(identifiers.raw_state) == "function"
    then
        local raw = store.read_raw()
        local ids_raw = identifiers.raw_state()
        if raw and raw == cached_users_raw and ids_raw ~= nil and ids_raw == cached_ids_raw then
            local cached_user = normalized ~= "" and cached_by_email[normalized] or nil
            if cached_user then
                return {user=cached_user, revision=cached_snapshot.revision}
            end
            return nil, "user absent from canonical directory"
        end
    end
    return store.with_lock(function()
        local snapshot, err = M.read_locked(false)
        if not snapshot then return nil, err end
        for _, user in ipairs(snapshot.users) do
            if user.source.email == normalized and normalized ~= "" then return {user=user, revision=snapshot.revision} end
        end
        return nil, "user absent from canonical directory"
    end)
end

return M
