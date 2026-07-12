from pathlib import Path

path = Path('.github/scripts/apply_user_avatar_thumbnails.py')
source = path.read_text(encoding='utf-8')
old = '''replace_count(
    "studio/nginx/lua/admin_api/available_users.lua",
    \'\'\'                            is_active = true,
                            status = "active"
\'\'\',
    \'\'\'                            is_active = true,
                            status = "active",
                            picture_url = picture_url(ud)
\'\'\',
    2,
)
'''
new = '''replace_once(
    "studio/nginx/lua/admin_api/available_users.lua",
    \'\'\'                            is_active = true,
                            status = "active"
\'\'\',
    \'\'\'                            is_active = true,
                            status = "active",
                            picture_url = picture_url(ud)
\'\'\',
)

replace_once(
    "studio/nginx/lua/admin_api/available_users.lua",
    \'\'\'                        is_active = true,
                        status = "active"
\'\'\',
    \'\'\'                        is_active = true,
                        status = "active",
                        picture_url = picture_url(ud)
\'\'\',
)
'''
if source.count(old) != 1:
    raise SystemExit('active user patch block not found exactly once')
exec(compile(source.replace(old, new), str(path), 'exec'))
