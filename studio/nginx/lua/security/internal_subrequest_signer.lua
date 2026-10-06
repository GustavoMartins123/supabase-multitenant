-- Assina subrequests internos destinados a Projects API via HMAC studio-nginx.
local projects_api_signer = require("security.projects_api_signer")

projects_api_signer.enforce()
