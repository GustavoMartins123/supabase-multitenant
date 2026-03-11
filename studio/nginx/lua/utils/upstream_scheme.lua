local proto = os.getenv("BACKEND_PROTO")
if proto == "https" then
    return "https"
end
return "http"
