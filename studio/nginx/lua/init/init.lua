local cookie_secret = os.getenv("COOKIE_SIGN_SECRET")
local service_key_encryption_key = os.getenv("STUDIO_SERVICE_KEY_ENCRYPTION_KEY")

if not cookie_secret or cookie_secret == "" then
    error("COOKIE_SIGN_SECRET is required")
end

if not service_key_encryption_key
    or #service_key_encryption_key ~= 44
    or not service_key_encryption_key:match("^[A-Za-z0-9_-]+=$")
then
    error("STUDIO_SERVICE_KEY_ENCRYPTION_KEY must be a valid Fernet key")
end

-- Global imutável compartilhada pelos handlers de contexto de projeto.
COOKIE_SECRET = cookie_secret
