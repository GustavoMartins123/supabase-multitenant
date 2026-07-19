import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../data/project_repository.dart';
import '../models/job.dart';
import '../models/restore_point.dart';
import '../providers/restore_points_provider.dart';
import '../providers/project_jobs_provider.dart';
import '../supabase_colors.dart';

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
      builder: (_) => _CreateRestorePointDialog(projectRef: widget.projectRef),
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
      itemBuilder: (_, i) => _buildFolderTile(data.points[i], busy),
    );
  }

  Widget _buildFolderTile(RestorePoint point, bool busy) {
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
              if (!busy && !point.isBusy)
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
                    if (val == 'restore') _restorePoint(point);
                    if (val == 'delete') _deletePoint(point);
                  },
                  itemBuilder: (_) => [
                    if (point.isReady)
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

class _CreateRestorePointDialog extends StatefulWidget {
  const _CreateRestorePointDialog({required this.projectRef});

  final String projectRef;

  @override
  State<_CreateRestorePointDialog> createState() =>
      _CreateRestorePointDialogState();
}

class _CreateRestorePointDialogState extends State<_CreateRestorePointDialog> {
  late final TextEditingController _titleCtrl;
  final _descriptionCtrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    _titleCtrl = TextEditingController(
      text: DateFormat('dd/MM/yyyy HH:mm').format(DateTime.now()),
    );
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descriptionCtrl.dispose();
    super.dispose();
  }

  void _submit() {
    if (_formKey.currentState!.validate()) {
      Navigator.pop(context, {
        'title': _titleCtrl.text.trim(),
        'description': _descriptionCtrl.text.trim(),
      });
    }
  }

  InputDecoration _fieldDecoration(String hint) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
      filled: true,
      fillColor: SupabaseColors.bg300,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: SupabaseColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: SupabaseColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: SupabaseColors.brand, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: SupabaseColors.error),
      ),
      contentPadding: const EdgeInsets.symmetric(
        horizontal: 12,
        vertical: 12,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 480),
        decoration: BoxDecoration(
          color: SupabaseColors.bg200,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: SupabaseColors.brand.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.create_new_folder_rounded,
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
                            'Novo ponto de restauração',
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
                const SizedBox(height: 20),
                const Text(
                  'Título',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: SupabaseColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _titleCtrl,
                  maxLength: 80,
                  decoration: _fieldDecoration('ex.: antes do deploy v2'),
                  style: const TextStyle(
                    fontSize: 13,
                    color: SupabaseColors.textPrimary,
                  ),
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? 'Informe um título'
                      : null,
                  onFieldSubmitted: (_) => _submit(),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Descrição (opcional)',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: SupabaseColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  controller: _descriptionCtrl,
                  maxLength: 400,
                  maxLines: 3,
                  decoration: _fieldDecoration('O que este ponto representa?'),
                  style: const TextStyle(
                    fontSize: 13,
                    color: SupabaseColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: SupabaseColors.info.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: SupabaseColors.info.withValues(alpha: 0.2),
                    ),
                  ),
                  child: const Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.info_outline_rounded,
                        color: SupabaseColors.info,
                        size: 16,
                      ),
                      SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'O ponto captura o banco de dados e os arquivos do '
                          'storage. Os serviços do projeto ficam pausados '
                          'durante a captura.',
                          style: TextStyle(
                            fontSize: 11,
                            height: 1.4,
                            color: SupabaseColors.textMuted,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                Row(
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
                      child: const Text(
                        'Cancelar',
                        style: TextStyle(fontSize: 13),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton.icon(
                      onPressed: _submit,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: SupabaseColors.brand,
                        foregroundColor: Colors.black,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(6),
                        ),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 10,
                        ),
                      ),
                      icon: const Icon(Icons.check_rounded, size: 16),
                      label: const Text(
                        'Criar ponto',
                        style: TextStyle(fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
