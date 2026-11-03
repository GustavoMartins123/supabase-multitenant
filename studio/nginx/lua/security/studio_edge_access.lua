require("security.csrf").enforce()
local context = require("security.project_access").enforce_admin()
if type(context) ~= "table" then return end
require("security.projects_api_signer").enforce()
