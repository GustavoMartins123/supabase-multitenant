local context = require("security.project_access").enforce()
if type(context) ~= "table" then return end
require("security.projects_api_signer").enforce()
