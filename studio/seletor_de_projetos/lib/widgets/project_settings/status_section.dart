import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/project_settings_provider.dart';
import '../../data/project_repository.dart';
import '../../supabase_colors.dart';
import '../../services/projectService.dart';
import '../action_button.dart';
import '../section_widget.dart';
import '../error_box.dart';
import '../../session.dart';
import '../../models/project_member.dart';

class StatusSection extends ConsumerStatefulWidget {
  final String projectRef;
  const StatusSection({super.key, required this.projectRef});

  @override
  ConsumerState<StatusSection> createState() => _StatusSectionState();
}

class _StatusSectionState extends ConsumerState<StatusSection> {
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _busy = Session().isBusy(widget.projectRef);
    Session().busyListenable.addListener(_onBusyChanged);
  }

  @override
  void dispose() {
    Session().busyListenable.removeListener(_onBusyChanged);
    super.dispose();
  }

  void _onBusyChanged() {
    final newBusy = Session().isBusy(widget.projectRef);
    if (newBusy != _busy) {
      setState(() => _busy = newBusy);
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(projectStatusProvider(widget.projectRef));
    final membersAsync = ref.watch(projectMembersProvider(widget.projectRef));

    final myId = Session().myId;
    final myRole =
        membersAsync.value
            ?.firstWhere(
              (m) => m.user_id == myId,
              orElse: () => ProjectMember(user_id: '', role: 'member'),
            )
            .role ??
        'member';
    final canManageProject = myRole == 'admin' || Session().isSysAdmin;

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
              if (canManageProject) ...[
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: ActionButton(
                        icon: Icons.play_arrow_rounded,
                        label: 'Start',
                        color: SupabaseColors.success,
                        onPressed: _busy ? null : () => _doAction('start'),
                        busy: _busy,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ActionButton(
                        icon: Icons.stop_rounded,
                        label: 'Stop',
                        color: SupabaseColors.error,
                        onPressed: _busy ? null : () => _doAction('stop'),
                        busy: _busy,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ActionButton(
                        icon: Icons.restart_alt_rounded,
                        label: 'Restart',
                        color: SupabaseColors.info,
                        onPressed: _busy ? null : () => _doAction('restart'),
                        busy: _busy,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ActionButton(
                        icon: Icons.refresh_rounded,
                        label: 'Recreate',
                        color: SupabaseColors.warning,
                        onPressed: _busy ? null : () => _doRecreate(),
                        busy: _busy,
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

  void _doAction(String action) async {
    final tracker = Session();
    if (tracker.isBusy(widget.projectRef)) return;

    tracker.setBusy(widget.projectRef, true);
    try {
      final result = await ref
          .read(projectRepositoryProvider)
          .doAction(widget.projectRef, action);
      final job = result.job;

      if (job != null) {
        final waited = await ProjectService.waitForJob(job.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                waited.message ??
                    (waited.ok
                        ? 'Ação $action executada'
                        : 'Falha ao executar $action'),
              ),
              backgroundColor: waited.ok
                  ? SupabaseColors.success
                  : SupabaseColors.error,
            ),
          );
        }
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(result.message ?? 'Ação $action executada'),
            backgroundColor: SupabaseColors.success,
          ),
        );
      }
      ref.invalidate(projectStatusProvider(widget.projectRef));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Erro: $e'),
            backgroundColor: SupabaseColors.error,
          ),
        );
      }
    } finally {
      tracker.setBusy(widget.projectRef, false);
    }
  }

  void _doRecreate() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: SupabaseColors.bg200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: const Row(
          children: [
            Icon(Icons.refresh_rounded, color: SupabaseColors.warning),
            SizedBox(width: 8),
            Text(
              'Recriar todos os serviços?',
              style: TextStyle(color: SupabaseColors.textPrimary),
            ),
          ],
        ),
        content: const Text(
          'Todos os containers serão destruídos e recriados (down + up). '
          'Isso aplica alterações no .env mas causa indisponibilidade temporária.',
          style: TextStyle(color: SupabaseColors.textSecondary, fontSize: 13),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: TextButton.styleFrom(
              foregroundColor: SupabaseColors.warning,
            ),
            child: const Text('Recriar'),
          ),
        ],
      ),
    );

    if (confirm != true || !mounted) return;

    final tracker = Session();
    if (tracker.isBusy(widget.projectRef)) return;

    tracker.setBusy(widget.projectRef, true);
    try {
      final allServices = [
        'auth',
        'rest',
        'storage',
        'imgproxy',
        'nginx',
        'meta',
      ];
      final result = await ref
          .read(projectRepositoryProvider)
          .recreateServices(widget.projectRef, allServices);

      final job = result.job;
      if (job != null) {
        final waited = await ProjectService.waitForJob(job.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                waited.message ??
                    (waited.ok
                        ? 'Serviços recriados com sucesso'
                        : 'Falha ao recriar serviços'),
              ),
              backgroundColor: waited.ok
                  ? SupabaseColors.success
                  : SupabaseColors.error,
            ),
          );
        }
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(result.message ?? 'Serviços recriados com sucesso'),
            backgroundColor: SupabaseColors.success,
          ),
        );
      }
      ref.invalidate(projectStatusProvider(widget.projectRef));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Erro ao recriar: $e'),
            backgroundColor: SupabaseColors.error,
          ),
        );
      }
    } finally {
      tracker.setBusy(widget.projectRef, false);
    }
  }
}
