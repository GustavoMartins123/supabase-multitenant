import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/project_settings_provider.dart';
import '../../data/project_repository.dart';
import '../../supabase_colors.dart';
import '../action_button.dart';
import '../section_widget.dart';
import '../error_box.dart';
import '../../session.dart';
import '../../models/project_member.dart';

class StatusSection extends ConsumerWidget {
  final String projectRef;
  const StatusSection({super.key, required this.projectRef});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(projectStatusProvider(projectRef));
    final membersAsync = ref.watch(projectMembersProvider(projectRef));
    final busy = Session().isBusy(projectRef);

    final myId = Session().myId;
    final myRole =
        membersAsync.value
            ?.firstWhere(
              (m) => m.user_id == myId,
              orElse: () => ProjectMember(user_id: '', role: 'member'),
            )
            .role ??
        'member';

    return SectionWidget(
      title: 'STATUS',
      child: statusAsync.when(
        loading: () => const Center(
          child: Padding(
            padding: EdgeInsets.all(20),
            child: SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SupabaseColors.brand,
              ),
            ),
          ),
        ),
        error: (err, _) => ErrorBox(message: 'Erro ao obter status: $err'),
        data: (st) {
          final isRunning = st.status == 'running';
          return Column(
            children: [
              Row(
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isRunning
                          ? SupabaseColors.success
                          : SupabaseColors.error,
                      boxShadow: [
                        BoxShadow(
                          color:
                              (isRunning
                                      ? SupabaseColors.success
                                      : SupabaseColors.error)
                                  .withValues(alpha: 0.5),
                          blurRadius: 8,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          st.status.toUpperCase(),
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: isRunning
                                ? SupabaseColors.success
                                : SupabaseColors.error,
                          ),
                        ),
                        Text(
                          '${st.running}/${st.total} containers ativos',
                          style: const TextStyle(
                            fontSize: 12,
                            color: SupabaseColors.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (myRole == 'admin') ...[
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: ActionButton(
                        icon: Icons.play_arrow_rounded,
                        label: 'Start',
                        color: SupabaseColors.success,
                        onPressed: busy
                            ? null
                            : () => _doAction(context, ref, 'start'),
                        busy: busy,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ActionButton(
                        icon: Icons.stop_rounded,
                        label: 'Stop',
                        color: SupabaseColors.error,
                        onPressed: busy
                            ? null
                            : () => _doAction(context, ref, 'stop'),
                        busy: busy,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ActionButton(
                        icon: Icons.restart_alt_rounded,
                        label: 'Restart',
                        color: SupabaseColors.info,
                        onPressed: busy
                            ? null
                            : () => _doAction(context, ref, 'restart'),
                        busy: busy,
                      ),
                    ),
                  ],
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  void _doAction(BuildContext context, WidgetRef ref, String action) async {
    final tracker = Session();
    if (tracker.isBusy(projectRef)) return;

    tracker.setBusy(projectRef, true);
    try {
      await ref.read(projectRepositoryProvider).doAction(projectRef, action);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Ação $action executada'),
            backgroundColor: SupabaseColors.success,
          ),
        );
      }
      ref.invalidate(projectStatusProvider(projectRef));
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Erro: $e'),
            backgroundColor: SupabaseColors.error,
          ),
        );
      }
    } finally {
      tracker.setBusy(projectRef, false);
    }
  }
}
