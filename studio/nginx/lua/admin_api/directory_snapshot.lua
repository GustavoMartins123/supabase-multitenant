local cjson = require("cjson.safe")
local store = require("admin_api.authelia_user_store")
local files = require("admin_api.authelia_file_store")
local identifiers = require("admin_api.authelia_identifiers")
local hmac = require("security.internal_hmac")
local admin_groups = require("security.admin_groups")
local identity = require("project_context.user_identity")
local M = {}
local sequence_path = "/config/.studio-directory-sequence"
local profile_fields = {"given_name", "family_name", "middle_name", "nickname", "picture", "website", "profile", "gender", "birthdate", "zoneinfo", "locale", "phone_number", "phone_extension"}
local address_fields = {"street_address", "locality", "region", "postal_code", "country"}

-- Caller must hold users_database.yml's lock. This is the only snapshot source.
function M.read_locked(assign_sequence)
    local data, raw, err = store.load()
    if not data then return nil, err end
    local revision, hash_err = hmac.sha256_hex(raw)
    if not revision then return nil, hash_err end
    assert(cjson.array_mt, "cjson array metatable is required")
    local users = setmetatable({}, cjson.array_mt)
    local seen_email = {}
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
            users[#users+1] = {
                id=user_id, username=username, display_name=attr.displayname or username,
                groups=groups, is_active=active and attr.disabled ~= true,
                source={name="studio_directory", email=email, profile=profile},
            }
        end
    end
    table.sort(users, function(a,b) return a.username < b.username end)
    local snapshot = {revision=revision, users=users}
    if assign_sequence then
        local file = io.open(sequence_path, "rb")
        if not file then return nil, "directory sequence unavailable; run installation configuration" end
        local raw_sequence = file:read("*a")
        file:close()
        local sequence = tonumber(raw_sequence)
        if not sequence or sequence < 0 or sequence % 1 ~= 0 or sequence >= 9007199254740991 then return nil, "invalid directory sequence" end
        sequence = sequence + 1
        local written, write_err = files.atomic_write(sequence_path, tostring(sequence), 438)
        if not written then return nil, write_err end
        snapshot.sequence = sequence
    end
    return snapshot
end

function M.for_email(email)
    return store.with_lock(function()
        local snapshot, err = M.read_locked(false)
        if not snapshot then return nil, err end
        local normalized = identity.normalize_email(email)
        for _, user in ipairs(snapshot.users) do
            if user.source.email == normalized and normalized ~= "" then return {user=user, revision=snapshot.revision} end
        end
        return nil, "user absent from canonical directory"
    end)
end

return M
