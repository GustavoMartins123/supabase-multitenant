from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {source.count(old)}")
    target.write_text(source.replace(old, new), encoding="utf-8")


def replace_count(path: str, old: str, new: str, count: int) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if source.count(old) != count:
        raise SystemExit(f"{path}: expected {count} occurrences, found {source.count(old)}")
    target.write_text(source.replace(old, new), encoding="utf-8")


replace_once(
    "studio/nginx/lua/init/init_worker.lua",
    '''                        user_uuid = user_uuid,
                    }''',
    '''                        user_uuid = user_uuid,
                        picture = attr.picture or "",
                    }''',
)

replace_once(
    "studio/nginx/lua/admin_api/user_avatar_handler.lua",
    '''    if method == "GET" then
        if requested_user_id and requested_user_id ~= profile.user_id then
            return respond_json(403, { error = "avatar access denied" })
        end
        return serve(path_or_err)
    end''',
    '''    if method == "GET" then
        local requested_path = path_or_err
        if requested_user_id then
            requested_path = avatar_path(requested_user_id)
            if not requested_path then
                return respond_json(400, { error = "invalid user identifier" })
            end
        end
        return serve(requested_path)
    end''',
)

replace_once(
    "studio/nginx/lua/admin_api/users_list.lua",
    '''                        status = user.is_active and "active" or "inactive",
                        email_hint = mask_email(user.email)
''',
    '''                        status = user.is_active and "active" or "inactive",
                        email_hint = mask_email(user.email),
                        picture_url = type(user.profile) == "table" and user.profile.picture or user.picture or ""
''',
)

replace_once(
    "studio/nginx/lua/admin_api/available_users.lua",
    '''local current = cjson.decode(res.body) or {}
local cache = ngx.shared.users_cache
''',
    '''local current = cjson.decode(res.body) or {}
local cache = ngx.shared.users_cache

local function picture_url(user)
    if type(user.profile) == "table" and user.profile.picture and user.profile.picture ~= "" then
        return user.profile.picture
    end
    return user.picture or ""
end
''',
)

replace_count(
    "studio/nginx/lua/admin_api/available_users.lua",
    '''                            is_active = true,
                            status = "active"
''',
    '''                            is_active = true,
                            status = "active",
                            picture_url = picture_url(ud)
''',
    2,
)

replace_once(
    "studio/nginx/lua/admin_api/available_users.lua",
    '''                                is_active = true,
                                status = "member"
''',
    '''                                is_active = true,
                                status = "member",
                                picture_url = picture_url(ud)
''',
)

replace_once(
    "studio/nginx/lua/admin_api/available_users.lua",
    '''                                is_active = true,
                                status = "available"
''',
    '''                                is_active = true,
                                status = "available",
                                picture_url = picture_url(ud)
''',
)

replace_once(
    "studio/nginx/lua/admin_api/project_members.lua",
    '''        m.is_active = ud.is_active
        m.status = ud.is_active and "active" or "inactive"
''',
    '''        m.is_active = ud.is_active
        m.status = ud.is_active and "active" or "inactive"
        m.picture_url = type(ud.profile) == "table" and ud.profile.picture or ud.picture or ""
''',
)

replace_once(
    "studio/seletor_de_projetos/lib/models/user_models.dart",
    '''  final String emailHint;

  UserInfo({''',
    '''  final String emailHint;
  final String? pictureUrl;

  UserInfo({''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/user_models.dart",
    '''    required this.emailHint,
  });''',
    '''    required this.emailHint,
    this.pictureUrl,
  });''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/user_models.dart",
    '''      emailHint: json['email_hint'] ?? '',
    );''',
    '''      emailHint: json['email_hint'] ?? '',
      pictureUrl: json['picture_url'] as String?,
    );''',
)

replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''  final String? note;

  AvailableUser({''',
    '''  final String? note;
  final String? pictureUrl;

  AvailableUser({''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''    this.note,
  });''',
    '''    this.note,
    this.pictureUrl,
  });''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''      note: json['note'],
    );''',
    '''      note: json['note'],
      pictureUrl: json['picture_url'] as String?,
    );''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''      if (note != null) 'note': note,
    };''',
    '''      if (note != null) 'note': note,
      if (pictureUrl != null) 'picture_url': pictureUrl,
    };''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''  final String displayName;

  AvailableUserShort({''',
    '''  final String displayName;
  final String? pictureUrl;

  AvailableUserShort({''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''    required this.displayName,
  });

  factory AvailableUserShort.fromJson''',
    '''    required this.displayName,
    this.pictureUrl,
  });

  factory AvailableUserShort.fromJson''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/AllUsers.dart",
    '''        displayName: j['display_name'] as String,
      );''',
    '''        displayName: j['display_name'] as String,
        pictureUrl: j['picture_url'] as String?,
      );''',
)

replace_once(
    "studio/seletor_de_projetos/lib/models/project_member.dart",
    '''  final String? displayName;

  ProjectMember({''',
    '''  final String? displayName;
  final String? pictureUrl;

  ProjectMember({''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/project_member.dart",
    '''    this.userHash,
  });''',
    '''    this.userHash,
    this.pictureUrl,
  });''',
)
replace_once(
    "studio/seletor_de_projetos/lib/models/project_member.dart",
    '''      role: json['role'] as String,
    );''',
    '''      role: json['role'] as String,
      pictureUrl: json['picture_url'] as String?,
    );''',
)

Path("studio/seletor_de_projetos/lib/widgets/user_avatar_thumbnail.dart").write_text(
    '''import 'package:flutter/material.dart';

class UserAvatarThumbnail extends StatelessWidget {
  const UserAvatarThumbnail({
    super.key,
    required this.pictureUrl,
    required this.size,
    required this.borderRadius,
    required this.backgroundColor,
    required this.fallback,
  });

  final String? pictureUrl;
  final double size;
  final BorderRadius borderRadius;
  final Color backgroundColor;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    final rawUrl = pictureUrl?.trim() ?? '';
    final fallbackWidget = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: borderRadius,
      ),
      alignment: Alignment.center,
      child: fallback,
    );

    if (rawUrl.isEmpty) return fallbackWidget;

    final resolvedUrl = Uri.base.resolve(rawUrl).toString();
    return ClipRRect(
      borderRadius: borderRadius,
      child: Image.network(
        resolvedUrl,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => fallbackWidget,
      ),
    );
  }
}
''',
    encoding="utf-8",
)

replace_once(
    "studio/seletor_de_projetos/lib/widgets/admin_users/user_card.dart",
    '''import '../../userProjectsAdminScreen.dart';
''',
    '''import '../../userProjectsAdminScreen.dart';
import '../user_avatar_thumbnail.dart';
''',
)
replace_once(
    "studio/seletor_de_projetos/lib/widgets/admin_users/user_card.dart",
    '''            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: user.isActive
                    ? SupabaseColors.success.withValues(alpha: 0.2)
                    : SupabaseColors.error.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Text(
                  isMe ? 'EU' : user.displayName.substring(0, 1).toUpperCase(),
                  style: TextStyle(
                    color: user.isActive
                        ? SupabaseColors.success
                        : SupabaseColors.error,
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
              ),
            ),''',
    '''            UserAvatarThumbnail(
              pictureUrl: user.pictureUrl,
              size: 44,
              borderRadius: BorderRadius.circular(8),
              backgroundColor: user.isActive
                  ? SupabaseColors.success.withValues(alpha: 0.2)
                  : SupabaseColors.error.withValues(alpha: 0.2),
              fallback: Text(
                isMe ? 'EU' : user.displayName.substring(0, 1).toUpperCase(),
                style: TextStyle(
                  color: user.isActive
                      ? SupabaseColors.success
                      : SupabaseColors.error,
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
            ),''',
)

replace_once(
    "studio/seletor_de_projetos/lib/dialogs/addMemberDialog.dart",
    '''import 'package:seletor_de_projetos/supabase_colors.dart';
''',
    '''import 'package:seletor_de_projetos/supabase_colors.dart';
import 'package:seletor_de_projetos/widgets/user_avatar_thumbnail.dart';
''',
)
replace_once(
    "studio/seletor_de_projetos/lib/dialogs/addMemberDialog.dart",
    '''                          Container(
                            width: 36,
                            height: 36,
                            decoration: BoxDecoration(
                              color: sel
                                  ? SupabaseColors.brand.withValues(alpha: 0.2)
                                  : SupabaseColors.surface200,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Center(
                              child: Text(
                                u.displayName[0].toUpperCase(),
                                style: TextStyle(
                                  color: sel
                                      ? SupabaseColors.brand
                                      : SupabaseColors.textSecondary,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 14,
                                ),
                              ),
                            ),
                          ),''',
    '''                          UserAvatarThumbnail(
                            pictureUrl: u.pictureUrl,
                            size: 36,
                            borderRadius: BorderRadius.circular(6),
                            backgroundColor: sel
                                ? SupabaseColors.brand.withValues(alpha: 0.2)
                                : SupabaseColors.surface200,
                            fallback: Text(
                              u.displayName[0].toUpperCase(),
                              style: TextStyle(
                                color: sel
                                    ? SupabaseColors.brand
                                    : SupabaseColors.textSecondary,
                                fontWeight: FontWeight.w600,
                                fontSize: 14,
                              ),
                            ),
                          ),''',
)

replace_once(
    "studio/seletor_de_projetos/lib/widgets/project_settings/members_section.dart",
    '''import '../../models/project_member.dart';
''',
    '''import '../../models/project_member.dart';
import '../user_avatar_thumbnail.dart';
''',
)
replace_once(
    "studio/seletor_de_projetos/lib/widgets/project_settings/members_section.dart",
    '''          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: member.role == 'admin'
                  ? SupabaseColors.warning.withValues(alpha: 0.2)
                  : SupabaseColors.info.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(
              member.role == 'admin'
                  ? Icons.admin_panel_settings_rounded
                  : Icons.person_rounded,
              color: member.role == 'admin'
                  ? SupabaseColors.warning
                  : SupabaseColors.info,
              size: 18,
            ),
          ),''',
    '''          UserAvatarThumbnail(
            pictureUrl: member.pictureUrl,
            size: 36,
            borderRadius: BorderRadius.circular(6),
            backgroundColor: member.role == 'admin'
                ? SupabaseColors.warning.withValues(alpha: 0.2)
                : SupabaseColors.info.withValues(alpha: 0.2),
            fallback: Icon(
              member.role == 'admin'
                  ? Icons.admin_panel_settings_rounded
                  : Icons.person_rounded,
              color: member.role == 'admin'
                  ? SupabaseColors.warning
                  : SupabaseColors.info,
              size: 18,
            ),
          ),''',
)

Path("tests/smoke/test_user_avatar_thumbnails.py").write_text(
    '''from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class UserAvatarThumbnailTests(unittest.TestCase):
    def test_cache_loads_picture_from_authelia(self) -> None:
        source = (ROOT / "studio/nginx/lua/init/init_worker.lua").read_text(encoding="utf-8")
        self.assertIn('picture = attr.picture or ""', source)

    def test_authenticated_avatar_handler_can_serve_requested_user(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")
        self.assertIn("requested_path = avatar_path(requested_user_id)", source)
        self.assertNotIn('avatar access denied', source)

    def test_user_lists_expose_picture_url(self) -> None:
        for relative in (
            "studio/nginx/lua/admin_api/users_list.lua",
            "studio/nginx/lua/admin_api/available_users.lua",
            "studio/nginx/lua/admin_api/project_members.lua",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("picture_url", source, relative)

    def test_flutter_models_parse_picture_url(self) -> None:
        for relative in (
            "studio/seletor_de_projetos/lib/models/user_models.dart",
            "studio/seletor_de_projetos/lib/models/AllUsers.dart",
            "studio/seletor_de_projetos/lib/models/project_member.dart",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("pictureUrl", source, relative)
            self.assertIn("picture_url", source, relative)

    def test_visible_user_lists_use_thumbnail_widget(self) -> None:
        for relative in (
            "studio/seletor_de_projetos/lib/widgets/admin_users/user_card.dart",
            "studio/seletor_de_projetos/lib/dialogs/addMemberDialog.dart",
            "studio/seletor_de_projetos/lib/widgets/project_settings/members_section.dart",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("UserAvatarThumbnail", source, relative)


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)
