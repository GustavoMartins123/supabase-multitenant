import 'package:flutter/material.dart';
import '../../supabase_colors.dart';
import '../../models/user_models.dart';
import '../../userProjectsAdminScreen.dart';

class UserCard extends StatelessWidget {
  const UserCard({
    super.key,
    required this.user,
    required this.onToggle,
    required this.isLoading,
    required this.isMe,
    required this.canToggle,
  });

  final UserInfo user;
  final VoidCallback onToggle;
  final bool isLoading;
  final bool isMe;
  final bool canToggle;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: isMe
            ? SupabaseColors.brand.withValues(alpha: 0.1)
            : SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isMe
              ? SupabaseColors.brand.withValues(alpha: 0.3)
              : SupabaseColors.border,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
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
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isMe ? '${user.displayName} (você)' : user.displayName,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      decoration: user.isActive
                          ? null
                          : TextDecoration.lineThrough,
                      color: SupabaseColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      const Icon(
                        Icons.account_circle_rounded,
                        size: 12,
                        color: SupabaseColors.textMuted,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        user.username,
                        style: const TextStyle(
                          fontSize: 12,
                          color: SupabaseColors.textMuted,
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Icon(
                        Icons.email_rounded,
                        size: 12,
                        color: SupabaseColors.textMuted,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          user.emailHint,
                          style: const TextStyle(
                            fontSize: 12,
                            color: SupabaseColors.textMuted,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: user.isActive
                          ? SupabaseColors.success.withValues(alpha: 0.15)
                          : SupabaseColors.error.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          user.isActive
                              ? Icons.check_circle_rounded
                              : Icons.block_rounded,
                          size: 12,
                          color: user.isActive
                              ? SupabaseColors.success
                              : SupabaseColors.error,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          user.status.toUpperCase(),
                          style: TextStyle(
                            color: user.isActive
                                ? SupabaseColors.success
                                : SupabaseColors.error,
                            fontWeight: FontWeight.w600,
                            fontSize: 10,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (isLoading)
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: SupabaseColors.brand.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: SupabaseColors.brand,
                  ),
                ),
              )
            else if (canToggle)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _IconBtn(
                    icon: Icons.folder_rounded,
                    tooltip: 'Ver projetos',
                    color: SupabaseColors.brand,
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => UserProjectsAdminScreen(
                            userIdHash: user.userUuid ?? user.id,
                            userName: user.username,
                          ),
                        ),
                      );
                    },
                  ),
                  const SizedBox(width: 6),
                  _IconBtn(
                    icon: user.isActive
                        ? Icons.block_rounded
                        : Icons.check_circle_rounded,
                    tooltip: user.isActive ? 'Desativar' : 'Ativar',
                    color: user.isActive
                        ? SupabaseColors.error
                        : SupabaseColors.success,
                    onPressed: onToggle,
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  const _IconBtn({
    required this.icon,
    required this.tooltip,
    required this.color,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Icon(icon, color: color, size: 18),
          ),
        ),
      ),
    );
  }
}
