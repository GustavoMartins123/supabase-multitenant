local cookie_secret = os.getenv("COOKIE_SIGN_SECRET")

if not cookie_secret or cookie_secret == "" then
    error("COOKIE_SIGN_SECRET is required")
end

-- Global imutável compartilhada pelos handlers de contexto de projeto.
COOKIE_SECRET = cookie_secret
