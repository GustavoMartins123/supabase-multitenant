import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/restore_point.dart';
import '../supabase_colors.dart';

class RestorePointCard extends StatelessWidget {
  const RestorePointCard({
    super.key,
    required this.point,
    required this.busy,
    required this.canRestore,
    required this.canDelete,
    this.onRestore,
    this.onDelete,
  });

  final RestorePoint point;
  final bool busy;
  final bool canRestore;
  final bool canDelete;
  final VoidCallback? onRestore;
  final VoidCallback? onDelete;

  String _formatBytes(int? bytes) {
    if (bytes == null || bytes <= 0) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    double value = bytes.toDouble();
    var unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    final text = value >= 100 || unit == 0
        ? value.toStringAsFixed(0)
        : value.toStringAsFixed(1);
    return '$text ${units[unit]}';
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '—';
    return DateFormat('dd/MM/yyyy HH:mm').format(date.toLocal());
  }

  Widget? _statusChip(RestorePoint point) {
    String? label;
    Color? color;
    switch (point.status) {
      case 'creating':
        label = 'CRIANDO';
        color = SupabaseColors.info;
        break;
      case 'restoring':
        label = 'RESTAURANDO';
        color = SupabaseColors.warning;
        break;
      case 'deleting':
        label = 'EXCLUINDO';
        color = SupabaseColors.warning;
        break;
      case 'failed':
        label = 'FALHOU';
        color = SupabaseColors.error;
        break;
    }
    if (label == null || color == null) return null;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 9,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
          color: color,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final statusChip = _statusChip(point);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                point.isAutomatic
                    ? Icons.folder_special_rounded
                    : Icons.folder_rounded,
                color: point.isFailed
                    ? SupabaseColors.error
                    : (point.isAutomatic
                        ? SupabaseColors.info
                        : SupabaseColors.brand),
                size: 30,
              ),
              const Spacer(),
              if (statusChip != null) statusChip,
              if (!busy && !point.isBusy && (canRestore || canDelete))
                PopupMenuButton<String>(
                  icon: const Icon(
                    Icons.more_vert_rounded,
                    color: SupabaseColors.textSecondary,
                    size: 18,
                  ),
                  color: SupabaseColors.bg300,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: const BorderSide(color: SupabaseColors.border),
                  ),
                  onSelected: (val) {
                    if (val == 'restore') onRestore?.call();
                    if (val == 'delete') onDelete?.call();
                  },
                  itemBuilder: (_) => [
                    if (point.isReady && canRestore)
                      const PopupMenuItem(
                        value: 'restore',
                        child: Row(
                          children: [
                            Icon(
                              Icons.settings_backup_restore_rounded,
                              size: 16,
                              color: SupabaseColors.textSecondary,
                            ),
                            SizedBox(width: 10),
                            Text(
                              'Restaurar',
                              style: TextStyle(
                                fontSize: 13,
                                color: SupabaseColors.textPrimary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    if (canDelete)
                      const PopupMenuItem(
                        value: 'delete',
                        child: Row(
                          children: [
                            Icon(
                              Icons.delete_outline_rounded,
                              size: 16,
                              color: SupabaseColors.error,
                            ),
                            SizedBox(width: 10),
                            Text(
                              'Excluir',
                              style: TextStyle(
                                fontSize: 13,
                                color: SupabaseColors.error,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 10),
          Tooltip(
            message: point.description?.isNotEmpty == true
                ? '${point.title}\n${point.description}'
                : point.title,
            waitDuration: const Duration(milliseconds: 400),
            child: Text(
              point.title,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: SupabaseColors.textPrimary,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (point.description?.isNotEmpty == true) ...[
            const SizedBox(height: 2),
            Text(
              point.description!,
              style: const TextStyle(
                fontSize: 11,
                color: SupabaseColors.textMuted,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const Spacer(),
          Tooltip(
            message: 'Criado por ${point.creatorName}',
            waitDuration: const Duration(milliseconds: 400),
            child: Row(
              children: [
                const Icon(
                  Icons.person_outline_rounded,
                  size: 12,
                  color: SupabaseColors.textMuted,
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    'Criado por ${point.creatorName}',
                    style: const TextStyle(
                      fontSize: 11,
                      color: SupabaseColors.textMuted,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 5),
          Row(
            children: [
              const Icon(
                Icons.schedule_rounded,
                size: 12,
                color: SupabaseColors.textMuted,
              ),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  _formatDate(point.createdAt),
                  style: const TextStyle(
                    fontSize: 11,
                    color: SupabaseColors.textMuted,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                _formatBytes(point.sizeBytes),
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: SupabaseColors.textSecondary,
                ),
              ),
            ],
          ),
          if (point.restoreCount > 0) ...[
            const SizedBox(height: 4),
            Row(
              children: [
                const Icon(
                  Icons.history_rounded,
                  size: 12,
                  color: SupabaseColors.info,
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    'Restaurado ${point.restoreCount}x'
                    '${point.lastRestoredAt != null ? ' · ${_formatDate(point.lastRestoredAt)}' : ''}',
                    style: const TextStyle(
                      fontSize: 10,
                      color: SupabaseColors.info,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ],
          if (point.isFailed && point.error != null) ...[
            const SizedBox(height: 4),
            Tooltip(
              message: point.error!,
              child: const Text(
                'Falhou — passe o mouse para detalhes',
                style: TextStyle(fontSize: 10, color: SupabaseColors.error),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
