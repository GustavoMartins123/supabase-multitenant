import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/project_repository.dart';
import '../models/job.dart';
import '../models/restore_point.dart';
import '../providers/restore_points_provider.dart';
import '../providers/project_jobs_provider.dart';
import '../supabase_colors.dart';
import 'create_restore_point_dialog.dart';
import 'restore_point_card.dart';

class RestorePointsDialog extends ConsumerStatefulWidget {
  const RestorePointsDialog({super.key, required this.projectRef});

  final String projectRef;

  @override
  ConsumerState<RestorePointsDialog> createState() =>
      _RestorePointsDialogState();
}

class _RestorePointsDialogState extends ConsumerState<RestorePointsDialog> {
  bool _working = false;
  String? _busyMessage;
  int? _busyProgress;

  void _snack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(color: Colors.white)),
        behavior: SnackBarBehavior.floating,
        backgroundColor: color,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }

  Future<void> _trackJob(
    Job job, {
    required String initialMessage,
    required String successMessage,
    required String failureMessage,
    required String action,
    int max = 400,
  }) async {
    setState(() {
      _working = true;
      _busyMessage = initialMessage;
      _busyProgress = null;
    });
    final result = await ref.read(projectJobsProvider.notifier).waitFor(
      job,
      project: widget.projectRef,
      action: action,
      max: max,
      onUpdate: (data) {
        if (!mounted) return;
        setState(() {
          _busyMessage = data['message']?.toString() ?? _busyMessage;
          _busyProgress = (data['progress'] as num?)?.toInt();
        });
      },
    );
    if (!mounted) return;
    setState(() {
      _working = false;
      _busyMessage = null;
      _busyProgress = null;
    });
    ref.invalidate(restorePointsProvider(widget.projectRef));
    if (result.ok) {
      _snack(successMessage, SupabaseColors.success);
    } else {
      _snack(
        result.message == null
            ? failureMessage
            : '$failureMessage\n${result.message}',
        SupabaseColors.error,
      );
    }
  }

  Future<void> _createPoint() async {
    final input = await showDialog<Map<String, String>>(
      context: context,
      builder: (_) => CreateRestorePointDialog(projectRef: widget.projectRef),
    );
    if (input == null || !mounted) return;
    try {
      final job = await ref.read(projectRepositoryProvider).createRestorePoint(
            widget.projectRef,
            title: input['title'],
            description: input['description'],
          );
      await _trackJob(
        job,
        initialMessage: 'Criando ponto de restauração...',
        successMessage: 'Ponto de restauração criado!',
        failureMessage: 'Falha ao criar ponto de restauração.',
        action: 'backup',
      );
    } catch (e) {
      _snack('Falha ao criar ponto: $e', SupabaseColors.error);
    }
  }

  Future<void> _restorePoint(RestorePoint point) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: SupabaseColors.surface200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: Row(
          children: [
            const Icon(
              Icons.settings_backup_restore_rounded,
              color: SupabaseColors.warning,
              size: 22,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'Restaurar "${point.title}"?',
                style: const TextStyle(
                  fontSize: 16,
                  color: SupabaseColors.textPrimary,
                ),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            Text(
              'Esta ação irá:',
              style: TextStyle(
                color: SupabaseColors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            SizedBox(height: 8),
            Text(
              '• Substituir o banco de dados e os arquivos do storage pelo conteúdo do ponto\n'
              '• Reverter usuários e sessões do Auth para o estado do ponto\n'
              '• Reiniciar os serviços do projeto (indisponibilidade temporária)\n'
              '• Criar antes um ponto automático de segurança com o estado atual',
              style: TextStyle(
                color: SupabaseColors.textSecondary,
                height: 1.5,
                fontSize: 13,
              ),
            ),
            SizedBox(height: 12),
            Text(
              'As chaves de API e a URL do projeto não mudam.',
              style: TextStyle(color: SupabaseColors.textMuted, fontSize: 12),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text(
              'Cancelar',
              style: TextStyle(color: SupabaseColors.textMuted),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: SupabaseColors.warning,
              foregroundColor: Colors.black,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(6),
              ),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Restaurar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final job = await ref
          .read(projectRepositoryProvider)
          .restoreRestorePoint(widget.projectRef, point.id);
      await _trackJob(
        job,
        initialMessage: 'Restaurando projeto...',
        successMessage: 'Projeto restaurado com sucesso!',
        failureMessage: 'Falha na restauração.',
        action: 'restore',
        max: 1300,
      );
    } catch (e) {
      _snack('Falha ao restaurar: $e', SupabaseColors.error);
    }
  }

  Future<void> _deletePoint(RestorePoint point) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: SupabaseColors.surface200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: const Row(
          children: [
            Icon(
              Icons.delete_outline_rounded,
              color: SupabaseColors.error,
              size: 22,
            ),
            SizedBox(width: 12),
            Text(
              'Excluir ponto',
              style: TextStyle(fontSize: 16, color: SupabaseColors.textPrimary),
            ),
          ],
        ),
        content: Text(
          'Excluir permanentemente o ponto "${point.title}"? '
          'Os arquivos de backup serão removidos do servidor.',
          style: const TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text(
              'Cancelar',
              style: TextStyle(color: SupabaseColors.textMuted),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: SupabaseColors.error,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(6),
              ),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Excluir'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final job = await ref
          .read(projectRepositoryProvider)
          .deleteRestorePoint(widget.projectRef, point.id);
      await _trackJob(
        job,
        initialMessage: 'Excluindo ponto de restauração...',
        successMessage: 'Ponto de restauração excluído.',
        failureMessage: 'Falha ao excluir ponto.',
        action: 'delete_restore_point',
      );
    } catch (e) {
      _snack('Falha ao excluir: $e', SupabaseColors.error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pointsAsync = ref.watch(restorePointsProvider(widget.projectRef));
    final activeJob = ref.watch(activeProjectJobProvider(widget.projectRef));
    final busy = _working || activeJob != null;

    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 760, maxHeight: 640),
        decoration: BoxDecoration(
          color: SupabaseColors.bg200,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildHeader(context),
            if (busy) _buildBusyBanner(activeJob),
            Flexible(
              child: pointsAsync.when(
                loading: () => _buildLoading(),
                error: (err, _) => _buildError(err.toString()),
                data: (data) => data.points.isEmpty
                    ? _buildEmpty()
                    : _buildGrid(data, busy),
              ),
            ),
            _buildFooter(pointsAsync.value, busy),
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
              Icons.settings_backup_restore_rounded,
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
                  'Pontos de restauração',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: SupabaseColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  widget.projectRef,
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

  Widget _buildBusyBanner(Job? activeJob) {
    final progress = _busyProgress ?? activeJob?.progress;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: SupabaseColors.info.withValues(alpha: 0.08),
        border: const Border(
          bottom: BorderSide(color: SupabaseColors.border),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: SupabaseColors.info,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _busyMessage ?? activeJob?.message ?? 'Processando...',
                  style: const TextStyle(
                    fontSize: 12,
                    color: SupabaseColors.textSecondary,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (progress != null)
                Text(
                  '$progress%',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: SupabaseColors.info,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: progress == null ? null : progress / 100,
              minHeight: 4,
              backgroundColor: SupabaseColors.bg300,
              color: SupabaseColors.info,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoading() {
    return const Padding(
      padding: EdgeInsets.all(60),
      child: Center(
        child: SizedBox(
          width: 32,
          height: 32,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: SupabaseColors.brand,
          ),
        ),
      ),
    );
  }

  Widget _buildError(String message) {
    return Padding(
      padding: const EdgeInsets.all(40),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              color: SupabaseColors.error,
              size: 32,
            ),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: SupabaseColors.textSecondary,
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 16),
            TextButton.icon(
              onPressed: () =>
                  ref.invalidate(restorePointsProvider(widget.projectRef)),
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    return Padding(
      padding: const EdgeInsets.all(48),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(
              Icons.folder_open_rounded,
              size: 40,
              color: SupabaseColors.textMuted,
            ),
            SizedBox(height: 16),
            Text(
              'Nenhum ponto de restauração ainda',
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: SupabaseColors.textPrimary,
              ),
            ),
            SizedBox(height: 6),
            Text(
              'Crie um ponto antes de subir mudanças para produção.\n'
              'Você poderá voltar o banco e o storage a este estado.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: SupabaseColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildGrid(RestorePointList data, bool busy) {
    return GridView.builder(
      shrinkWrap: true,
      padding: const EdgeInsets.all(20),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 235,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        mainAxisExtent: 220,
      ),
      itemCount: data.points.length,
      itemBuilder: (_, i) {
        final point = data.points[i];
        return RestorePointCard(
          point: point,
          busy: busy,
          canRestore: data.canRestore,
          canDelete: data.canDelete,
          onRestore: () => _restorePoint(point),
          onDelete: () => _deletePoint(point),
        );
      },
    );
  }

  Widget _buildFooter(RestorePointList? data, bool busy) {
    final count = data?.activeCount ?? 0;
    final limit = data?.limit ?? 15;
    final atLimit = count >= limit;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: SupabaseColors.border)),
      ),
      child: Row(
        children: [
          Text(
            '$count de $limit pontos',
            style: TextStyle(
              fontSize: 12,
              color:
                  atLimit ? SupabaseColors.warning : SupabaseColors.textMuted,
            ),
          ),
          const Spacer(),
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
          const SizedBox(width: 8),
          if (data?.canCreate == true)
            ElevatedButton.icon(
              onPressed: busy || atLimit ? null : _createPoint,
              style: ElevatedButton.styleFrom(
                backgroundColor: SupabaseColors.brand,
                foregroundColor: Colors.black,
                disabledBackgroundColor: SupabaseColors.bg300,
                disabledForegroundColor: SupabaseColors.textMuted,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(6),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
              ),
              icon: const Icon(Icons.create_new_folder_rounded, size: 16),
              label: const Text('Criar ponto', style: TextStyle(fontSize: 13)),
            ),
        ],
      ),
    );
  }
}
