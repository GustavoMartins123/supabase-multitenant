local lfs = require("lfs")

local M = {}

local SNIPPETS_DIR = os.getenv("SNIPPETS_MANAGEMENT_FOLDER") or "/app/snippets"
local cache = ngx.shared.service_keys

local function acquire_lock(key, timeout_seconds, exptime_seconds)
    if not cache then
        return function() end
    end

    local token = table.concat({
        tostring(ngx.now()),
        tostring(math.random()),
        tostring(coroutine.running() or "main"),
    }, ":")
    local deadline = ngx.now() + timeout_seconds

    repeat
        local acquired, err = cache:add(key, token, exptime_seconds)
        if acquired then
            return function()
                if cache:get(key) == token then
                    cache:delete(key)
                end
            end
        end
        if err and err ~= "exists" then
            return nil, err
        end
        ngx.sleep(0.01)
    until ngx.now() >= deadline

    return nil, "timeout"
end

local function mode(path)
    return lfs.attributes(path, "mode")
end

local function join(left, right)
    return left .. "/" .. right
end

local function read_file(path)
    local file, err = io.open(path, "rb")
    if not file then
        return nil, err
    end
    local content = file:read("*a")
    file:close()
    return content
end

local function files_equal(left, right)
    local left_size = lfs.attributes(left, "size")
    local right_size = lfs.attributes(right, "size")
    if left_size == nil or right_size == nil or left_size ~= right_size then
        return false
    end

    local left_content = read_file(left)
    local right_content = read_file(right)
    return left_content ~= nil and right_content ~= nil and left_content == right_content
end

local function directory_entries(path)
    local entries = {}
    for entry in lfs.dir(path) do
        if entry ~= "." and entry ~= ".." then
            table.insert(entries, entry)
        end
    end
    table.sort(entries)
    return entries
end

local function directory_is_empty(path)
    for entry in lfs.dir(path) do
        if entry ~= "." and entry ~= ".." then
            return false
        end
    end
    return true
end

local function safe_label(value)
    local label = tostring(value or "legacy"):gsub("[^%w._-]", "_")
    if label == "" then
        return "legacy"
    end
    return label
end

local function conflict_target(target_dir, filename, label, source_path)
    local stem, extension = filename:match("^(.*)(%.[^.]*)$")
    if not stem then
        stem = filename
        extension = ""
    end

    local base = stem .. "__legacy_" .. safe_label(label)
    for index = 0, 999 do
        local suffix = index == 0 and "" or ("_" .. tostring(index))
        local candidate = join(target_dir, base .. suffix .. extension)
        local candidate_mode = mode(candidate)
        if not candidate_mode then
            return candidate, false
        end
        if mode(source_path) == "file" and candidate_mode == "file"
            and files_equal(source_path, candidate)
        then
            return candidate, true
        end
    end
    return nil, false
end

local function move_entry(source_path, target_path, target_dir, filename, label, stats)
    local source_mode = mode(source_path)
    local target_mode = mode(target_path)
    if not source_mode then
        return true
    end

    if not target_mode then
        local ok, err = os.rename(source_path, target_path)
        if not ok then
            return nil, err or "rename failed"
        end
        stats.moved_entries = stats.moved_entries + 1
        return true
    end

    if source_mode == "file" and target_mode == "file" and files_equal(source_path, target_path) then
        local ok, err = os.remove(source_path)
        if not ok then
            return nil, err or "failed to remove duplicate"
        end
        stats.identical_duplicates = stats.identical_duplicates + 1
        return true
    end

    local preserved_path, already_preserved = conflict_target(
        target_dir,
        filename,
        label,
        source_path
    )
    if not preserved_path then
        return nil, "could not allocate a conflict-safe filename"
    end

    if already_preserved then
        local ok, err = os.remove(source_path)
        if not ok then
            return nil, err or "failed to remove preserved duplicate"
        end
        stats.identical_duplicates = stats.identical_duplicates + 1
        return true
    end

    local ok, err = os.rename(source_path, preserved_path)
    if not ok then
        return nil, err or "failed to preserve conflicting entry"
    end
    stats.conflicts_preserved = stats.conflicts_preserved + 1
    ngx.log(
        ngx.WARN,
        "[CONTENT-MIGRATION] Preserved conflicting snippet as ",
        preserved_path
    )
    return true
end

local function merge_directory(source, target, label, stats)
    if mode(source) ~= "directory" then
        return true
    end

    local target_mode = mode(target)
    if not target_mode then
        local ok, err = os.rename(source, target)
        if not ok then
            return nil, err or "directory rename failed"
        end
        stats.renamed_directories = stats.renamed_directories + 1
        return true
    end
    if target_mode ~= "directory" then
        return nil, "namespace target exists and is not a directory: " .. target
    end

    for _, entry in ipairs(directory_entries(source)) do
        local source_path = join(source, entry)
        local target_path = join(target, entry)
        local ok, err = move_entry(
            source_path,
            target_path,
            target,
            entry,
            label,
            stats
        )
        if not ok then
            return nil, source_path .. ": " .. (err or "merge failed")
        end
    end

    if directory_is_empty(source) then
        local ok, err = lfs.rmdir(source)
        if not ok then
            return nil, err or ("failed to remove empty legacy directory " .. source)
        end
        stats.removed_directories = stats.removed_directories + 1
    end

    return true
end

local function collect_plans(user_id, project_id, aliases)
    local plans = {}
    local seen_sources = {}
    local target_root_name = user_id .. "__" .. project_id

    if mode(SNIPPETS_DIR) ~= "directory" then
        return plans
    end

    local top_level = directory_entries(SNIPPETS_DIR)
    for _, alias in ipairs(aliases or {}) do
        if alias ~= project_id then
            local legacy_root_name = user_id .. "__" .. alias
            local legacy_prefix = legacy_root_name .. "__"

            for _, entry in ipairs(top_level) do
                local target_name
                if entry == legacy_root_name then
                    target_name = target_root_name
                elseif entry:sub(1, #legacy_prefix) == legacy_prefix then
                    target_name = target_root_name .. "__" .. entry:sub(#legacy_prefix + 1)
                end

                if target_name and not seen_sources[entry] then
                    local source = join(SNIPPETS_DIR, entry)
                    if mode(source) == "directory" then
                        seen_sources[entry] = true
                        table.insert(plans, {
                            source = source,
                            target = join(SNIPPETS_DIR, target_name),
                            alias = alias,
                        })
                    end
                end
            end
        end
    end

    table.sort(plans, function(left, right)
        return left.source < right.source
    end)
    return plans
end

local function migration_marker(user_id, identity)
    return table.concat({
        "content:namespace-migrated",
        user_id,
        identity.project_id,
        identity.current_ref,
    }, ":")
end

function M.ensure(user_id, identity)
    if not user_id or user_id == "" then
        return nil, "user id is missing"
    end
    if type(identity) ~= "table" or not identity.project_id then
        return nil, "project identity is missing"
    end

    local marker = migration_marker(user_id, identity)
    if cache and cache:get(marker) then
        return true
    end

    if mode(SNIPPETS_DIR) ~= "directory" then
        if cache then
            cache:set(marker, true, 30)
        end
        return true
    end

    local release_lock, lock_err = acquire_lock(marker .. ":lock", 2, 10)
    if not release_lock then
        return nil, "failed to acquire migration lock: " .. (lock_err or "timeout")
    end

    if cache and cache:get(marker) then
        release_lock()
        return true
    end

    local stats = {
        renamed_directories = 0,
        removed_directories = 0,
        moved_entries = 0,
        identical_duplicates = 0,
        conflicts_preserved = 0,
    }

    local ok = true
    local failure
    for _, plan in ipairs(collect_plans(user_id, identity.project_id, identity.aliases)) do
        local merged, merge_err = merge_directory(
            plan.source,
            plan.target,
            plan.alias,
            stats
        )
        if not merged then
            ok = false
            failure = merge_err or "namespace merge failed"
            break
        end
    end

    if ok and cache then
        cache:set(marker, true, 30)
    end

    release_lock()

    if not ok then
        return nil, failure
    end

    if stats.renamed_directories > 0
        or stats.removed_directories > 0
        or stats.moved_entries > 0
        or stats.identical_duplicates > 0
        or stats.conflicts_preserved > 0
    then
        ngx.log(
            ngx.NOTICE,
            "[CONTENT-MIGRATION] user=", user_id,
            " project_id=", identity.project_id,
            " renamed_dirs=", stats.renamed_directories,
            " removed_dirs=", stats.removed_directories,
            " moved_entries=", stats.moved_entries,
            " identical=", stats.identical_duplicates,
            " conflicts_preserved=", stats.conflicts_preserved
        )
    end

    return true, stats
end

return M
