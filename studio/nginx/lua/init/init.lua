local service_key_encryption_key = os.getenv("STUDIO_SERVICE_KEY_ENCRYPTION_KEY")

if not service_key_encryption_key
    or #service_key_encryption_key ~= 44
    or not service_key_encryption_key:match("^[A-Za-z0-9_-]+=$")
then
    error("STUDIO_SERVICE_KEY_ENCRYPTION_KEY must be a valid Fernet key")
end
