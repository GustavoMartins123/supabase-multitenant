if not ngx.var.cookie_supabase_project then
    return ""
end
return "supabase_project=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
