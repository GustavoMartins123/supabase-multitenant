local cjson = require("cjson.safe")
local store = require("admin_api.authelia_user_store")
local directory = require("admin_api.directory_snapshot")
local sync = require("admin_api.user_sync")
local cache = ngx.shared.users_cache

local function reconcile(premature)
    if premature then return end
    local ok, err = store.with_lock(function()
        local snapshot, read_err = directory.read_locked(false)
        if not snapshot then return nil, read_err end
        -- Cache is a projection for UI only, never authorization evidence.
        local old = cjson.decode(cache:get("__yaml_user_keys") or "[]")
        if type(old) ~= "table" then return nil, "invalid cache manifest" end
        local keys = {}
        for _, user in ipairs(snapshot.users) do
            local groups = table.concat(user.groups, ",")
            local encoded = cjson.encode({
                email=user.source.email, username=user.username,
                display_name=user.display_name, user_uuid=user.id,
                is_active=user.is_active, is_admin=require("security.admin_groups").is_admin(groups),
                picture=user.source.profile.picture,
            })
            assert(cache:set(user.id, encoded))
            keys[#keys+1] = user.id
            if user.source.email ~= "" then
                local key = "email:" .. user.source.email
                assert(cache:set(key, user.id))
                keys[#keys+1] = key
            end
        end
        local current = {}
        for _, key in ipairs(keys) do current[key] = true end
        for _, key in ipairs(old) do if not current[key] then cache:delete(key) end end
        assert(cache:set("__yaml_user_keys", cjson.encode(keys)))
        -- YAML is the durable outbox. Every cycle rereads it, including disabled
        -- entries and removals, retrying indefinitely after restart/outages.
        return sync.sync_directory()
    end)
    if not ok then ngx.log(ngx.ERR, "[DIRECTORY] Reconciliation pending: ", err) end
end

if ngx.worker.id() == 0 then
    local ok, err = ngx.timer.at(0, reconcile)
    if not ok then error(err) end
    ok, err = ngx.timer.every(5, reconcile)
    if not ok then error(err) end
end
