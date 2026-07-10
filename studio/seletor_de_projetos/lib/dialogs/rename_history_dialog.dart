import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/project_collaboration.dart';
import '../providers/project_collaboration_provider.dart';
import '../supabase_colors.dart';

class RenameHistoryDialog extends ConsumerWidget {
  const RenameHistoryDialog({super.key, required this.projectName});

  final String projectName;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(projectRenameHistoryProvider(projectName));

    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 560, maxHeight: 640),
        decoration: BoxDecoration(
          color: SupabaseColors.bg200,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildHeader(context),
            Flexible(
              child: history.when(
                loading: () => _buildLoading(),
                error: (err, _) => _buildError(context, ref, err.toString()),
                data: (events) =>
                    events.isEmpty ? _buildEmpty() : _buildList(events),
              ),
            ),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: SupabaseColors.border)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    style: TextButton.styleFrom(
                      foregroundColor: SupabaseColors.textSecondary,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 10,
                      ),
                    ),
                    child: const Text('Fechar', style: TextStyle(fontSize: 13)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: SupabaseColors.border)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: SupabaseColors.brand.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(
              Icons.history_rounded,
              color: SupabaseColors.brand,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Histórico de identidade',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: SupabaseColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  projectName,
                  style: const TextStyle(
                    fontSize: 12,
                    fontFamily: 'monospace',
                    color: SupabaseColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          InkWell(
            onTap: () => Navigator.pop(context),
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(
                Icons.close_rounded,
                size: 18,
                color: SupabaseColors.textMuted,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoading() {
    return const SizedBox(
      height: 220,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: 32,
              height: 32,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SupabaseColors.brand,
              ),
            ),
            SizedBox(height: 16),
            Text(
              'Carregando histórico...',
              style: TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError(BuildContext context, WidgetRef ref, String message) {
    return SizedBox(
      height: 220,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.error_outline_rounded,
                color: SupabaseColors.error,
                size: 30,
              ),
              const SizedBox(height: 12),
              Text(
                message,
                style: const TextStyle(color: SupabaseColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              TextButton.icon(
                onPressed: () => ref.invalidate(
                  projectRenameHistoryProvider(projectName),
                ),
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    return const SizedBox(
      height: 220,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.event_note_rounded,
              color: SupabaseColors.textMuted,
              size: 32,
            ),
            SizedBox(height: 12),
            Text(
              'Nenhuma alteração registrada ainda.',
              style: TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildList(List<ProjectRenameEvent> events) {
    return ListView.separated(
      padding: const EdgeInsets.all(20),
      itemCount: events.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (_, i) => _EventCard(event: events[i]),
    );
  }
}

class _EventCard extends StatelessWidget {
  const _EventCard({required this.event});
  final ProjectRenameEvent event;

  Color get _accent {
    switch (event.action) {
      case 'project_rename_succeeded':
        return SupabaseColors.success;
      case 'project_rename_failed':
        return SupabaseColors.error;
      case 'project_rename_rolled_back':
        return SupabaseColors.warning;
      case 'project_rename_started':
        return SupabaseColors.warning;
      case 'project_display_name_changed':
        return SupabaseColors.brand;
      default:
        return SupabaseColors.textSecondary;
    }
  }

  IconData get _icon {
    switch (event.action) {
      case 'project_rename_succeeded':
        return Icons.check_circle_outline_rounded;
      case 'project_rename_failed':
        return Icons.error_outline_rounded;
      case 'project_rename_rolled_back':
        return Icons.undo_rounded;
      case 'project_rename_started':
        return Icons.play_circle_outline_rounded;
      case 'project_display_name_changed':
        return Icons.label_outline_rounded;
      default:
        return Icons.history_rounded;
    }
  }

  String _formatDate(DateTime value) {
    final local = value.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(local.day)}/${two(local.month)}/${local.year} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.bg300.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_icon, color: _accent, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  event.label,
                  style: TextStyle(
                    color: _accent,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              Text(
                _formatDate(event.createdAt),
                style: const TextStyle(
                  color: SupabaseColors.textMuted,
                  fontSize: 11,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'por ${event.actorName}',
            style: const TextStyle(
              color: SupabaseColors.textSecondary,
              fontSize: 12,
            ),
          ),
          if (_hasDiff) ...[
            const SizedBox(height: 10),
            _buildDiffRow(),
          ],
        ],
      ),
    );
  }

  bool get _hasDiff {
    return (event.oldValue != null && event.oldValue!.isNotEmpty) ||
        (event.newValue != null && event.newValue!.isNotEmpty);
  }

  Widget _buildDiffRow() {
    final oldText = _formatValue(event.oldValue);
    final newText = _formatValue(event.newValue);

    if (oldText == null && newText == null) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: SupabaseColors.bg200,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: oldText != null
                ? Text(
                    oldText,
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textMuted,
                    ),
                  )
                : const Text(
                    '(vazio)',
                    style: TextStyle(
                      fontSize: 12,
                      color: SupabaseColors.textMuted,
                    ),
                  ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8),
            child: Icon(
              Icons.arrow_forward_rounded,
              size: 14,
              color: SupabaseColors.textMuted,
            ),
          ),
          Expanded(
            child: newText != null
                ? Text(
                    newText,
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textPrimary,
                    ),
                  )
                : const Text(
                    '(vazio)',
                    style: TextStyle(
                      fontSize: 12,
                      color: SupabaseColors.textMuted,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  String? _formatValue(Map<String, dynamic>? value) {
    if (value == null || value.isEmpty) return null;
    if (value.length == 1) {
      final entry = value.entries.first;
      final v = entry.value;
      if (v is String) return v.isEmpty ? '(vazio)' : v;
      return '${entry.key}: $v';
    }
    return value.entries.map((e) {
      final v = e.value;
      final text = v is String ? v : v.toString();
      final compact = text.length > 160 ? '${text.substring(0, 160)}…' : text;
      return '${e.key}: $compact';
    }).join('\n');
  }
}
