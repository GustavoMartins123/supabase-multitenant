local M = {}

function M.resolve(project_ref)
    local context = ngx.ctx.studio_project_context
    if type(project_ref) ~= "string" or not project_ref:match("^[a-z]+$") or #project_ref ~= 20 then
        return nil, "invalid public project reference"
    end
    if type(context) ~= "table" or context.ref ~= project_ref
        or type(context.project_uuid) ~= "string"
        or not context.project_uuid:match("^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$")
        or #context.project_uuid ~= 36 then
        return nil, "verified project context is required"
    end
    return { project_id = context.project_uuid, current_ref = context.ref }
end

return M
