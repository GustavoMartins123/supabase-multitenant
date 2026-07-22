import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:jwt_decoder/jwt_decoder.dart';

import 'supabase_colors.dart';
import 'session.dart';
import 'data/project_repository.dart';
import 'providers/config_provider.dart';
import 'providers/project_settings_provider.dart';
import 'providers/project_list_provider.dart';
import 'providers/project_jobs_provider.dart';
import 'services/projectService.dart';
import 'dialogs/transferProjectDialog.dart';
import 'dialogs/rename_project_dialog.dart';
import 'dialogs/rename_history_dialog.dart';

import 'widgets/close_button_widget.dart';
import 'widgets/icon_button_widget.dart';
import 'widgets/primary_button.dart';
import 'widgets/secondary_button.dart';
import 'widgets/danger_button.dart';
import 'widgets/section_widget.dart';
import 'widgets/project_settings/status_section.dart';
import 'widgets/project_settings/members_section.dart';
import 'widgets/project_settings/env_settings_section.dart';
import 'widgets/project_settings/user_telemetry_section.dart';
import 'models/project_member.dart';
import 'models/AllUsers.dart';

class ProjectSettingsDialog extends ConsumerStatefulWidget {
  const ProjectSettingsDialog({
    super.key,
    required this.ref,
    required this.anonKey,
    this.displayName,
  });

  final String ref;
  final String anonKey;
  final String? displayName;

  @override
  ConsumerState<ProjectSettingsDialog> createState() =>
      _ProjectSettingsDialogState();
}

class _ProjectSettingsDialogState extends ConsumerState<ProjectSettingsDialog>
    with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  late Animation<double> _fadeAnimation;

  late String _currentAnonKey;
  late String _currentConfigToken;
  String? _currentDisplayName;
  late final TextEditingController _displayNameController;
  bool _rotatingKey = false;
  bool _savingDisplayName = false;
  bool _loadingConfigToken = false;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animController,
      curve: Curves.easeOut,
    );
    _animController.forward();

    _currentAnonKey = widget.anonKey;
    _currentConfigToken = '';
    _currentDisplayName = widget.displayName;
    _displayNameController = TextEditingController(
      text: widget.displayName ?? '',
    );
  }

  @override
  void dispose() {
    _displayNameController.dispose();
    _animController.dispose();
    super.dispose();
  }

  Future<void> _saveDisplayName() async {
    final newName = _displayNameController.text.trim();
    if (newName == (_currentDisplayName ?? '')) {
      return;
    }
    setState(() => _savingDisplayName = true);
    try {
      final saved = await ref
          .read(projectRepositoryProvider)
          .updateProjectDisplayName(widget.ref, newName);
      if (!mounted) return;
      setState(() {
        _currentDisplayName = saved;
        _displayNameController.text = _currentDisplayName ?? '';
      });
      await ref.read(projectListProvider.notifier).refresh();
      if (!mounted) return;
      _showSnack('Nome de exibição atualizado.', SupabaseColors.success);
    } catch (e) {
      final msg = e.toString().replaceFirst('Exception: ', '');
      _showSnack('Erro ao atualizar nome: $msg', SupabaseColors.error);
    } finally {
      if (mounted) setState(() => _savingDisplayName = false);
    }
  }

  Future<void> _openRenameDialog() async {
    final result = await showDialog<RenameProjectResult>(
      context: context,
      builder: (_) => RenameProjectDialog(
        projectName: widget.ref,
        currentDisplayName: _currentDisplayName,
      ),
    );
    if (result == null) return;
    if (!mounted) return;
    await ref.read(projectListProvider.notifier).refresh();
    if (!mounted) return;
    Navigator.of(context).pop(result.newName);
  }

  void _openHistoryDialog() {
    showDialog(
      context: context,
      builder: (_) => RenameHistoryDialog(projectName: widget.ref),
    );
  }

  void _showSnack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(color: Colors.white)),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }

  Future<void> _rotateKey() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: SupabaseColors.bg200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: const Row(
          children: [
            Icon(Icons.warning_rounded, color: SupabaseColors.warning),
            SizedBox(width: 8),
            Text(
              'Gerar nova chave?',
              style: TextStyle(color: SupabaseColors.textPrimary),
            ),
          ],
        ),
        content: const Text(
          'A chave atual será invalidada. Apps usando ela vão parar de funcionar até serem atualizados.',
          style: TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(
              foregroundColor: SupabaseColors.warning,
            ),
            child: const Text('Gerar'),
          ),
        ],
      ),
    );

    if (confirm != true || !mounted) return;

    setState(() => _rotatingKey = true);
    try {
      final job =
          await ref.read(projectRepositoryProvider).rotateKey(widget.ref);
      final result = await ref.read(projectJobsProvider.notifier).waitFor(
            job,
            project: widget.ref,
            action: 'rotate_key',
          );
      if (!mounted) return;
      if (!result.ok) {
        _showSnack(
          result.message ?? 'Falha ao rotacionar as chaves.',
          SupabaseColors.error,
        );
        return;
      }

      await ref.read(projectListProvider.notifier).refresh(throwOnError: true);
      if (!mounted) return;
      final projects = ref.read(projectListProvider).requireValue;
      String? newKey;
      for (final project in projects) {
        if (project['name'] == widget.ref) {
          newKey = project['anon_token']?.toString();
          break;
        }
      }
      if (newKey == null || newKey.isEmpty) {
        throw Exception('Nova chave não retornada pela listagem de projetos');
      }
      setState(() => _currentAnonKey = newKey!);

      _showSnack('Nova chave gerada!', SupabaseColors.success);
    } catch (e) {
      _showSnack('Erro ao gerar chave: $e', SupabaseColors.error);
    } finally {
      if (mounted) setState(() => _rotatingKey = false);
    }
  }

  Future<void> _loadConfigToken() async {
    setState(() => _loadingConfigToken = true);
    try {
      final token = await ref
          .read(projectRepositoryProvider)
          .fetchProjectConfigToken(widget.ref);
      if (!mounted) return;
      setState(() => _currentConfigToken = token);
    } catch (e) {
      _showSnack(
        'Erro ao carregar token: ${e.toString().replaceFirst('Exception: ', '')}',
        SupabaseColors.error,
      );
    } finally {
      if (mounted) setState(() => _loadingConfigToken = false);
    }
  }

  Future<void> _deleteProject() async {
    bool sucesso = await ProjectService.confirmAndDeleteProject(
      context,
      widget.ref,
      submittedJobWaiter: (job) =>
          ref.read(projectJobsProvider.notifier).waitFor(
                job,
                project: widget.ref,
                action: 'delete',
                max: 400,
              ),
    );
    if (sucesso && mounted) Navigator.of(context).pop(widget.ref);
  }

  @override
  Widget build(BuildContext context) {
    final configAsync = ref.watch(configProvider);
    final serverDomain = configAsync.value?['server_domain'] as String? ?? '';
    final projectUrl =
        serverDomain.isNotEmpty ? '$serverDomain/${widget.ref}' : widget.ref;

    final membersAsync = ref.watch(projectMembersProvider(widget.ref));
    final activeJob = ref.watch(activeProjectJobProvider(widget.ref));
    final projectBusy = activeJob != null;
    final myId = Session().myId;
    final myRole = membersAsync.value
        ?.firstWhere(
          (m) => m.user_id == myId,
          orElse: () => ProjectMember(user_id: '', role: 'member'),
        )
        .role;

    if (myRole == null && membersAsync.isLoading) {
      return _buildLoadingDialog();
    }

    return Dialog(
      backgroundColor: Colors.transparent,
      child: FadeTransition(
        opacity: _fadeAnimation,
        child: Container(
          constraints: BoxConstraints(
            maxWidth: 720,
            maxHeight: MediaQuery.of(context).size.height * 0.9,
          ),
          decoration: BoxDecoration(
            color: SupabaseColors.bg200,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: SupabaseColors.border),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildHeader(),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      StatusSection(projectRef: widget.ref),
                      const SizedBox(height: 20),
                      _buildUrlSection(projectUrl),
                      const SizedBox(height: 20),
                      _buildIdentitySection(myRole, projectBusy),
                      const SizedBox(height: 20),
                      _buildAnonKeySection(myRole, projectBusy),
                      const SizedBox(height: 20),
                      if (myRole == 'admin' || Session().isSysAdmin) ...[
                        UserTelemetrySection(projectRef: widget.ref),
                        const SizedBox(height: 20),
                        _buildConfigTokenSection(),
                        const SizedBox(height: 20),
                      ],
                      EnvSettingsSection(
                        projectRef: widget.ref,
                        isAdmin: myRole == 'admin' || Session().isSysAdmin,
                      ),
                      const SizedBox(height: 20),
                      MembersSection(projectRef: widget.ref),
                    ],
                  ),
                ),
              ),
              _buildFooter(myRole, projectBusy),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
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
              Icons.settings_rounded,
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
                  'Configurações',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    letterSpacing: 0.5,
                    color: SupabaseColors.textMuted,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  widget.ref,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: SupabaseColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
          CloseButtonWidget(onPressed: () => Navigator.pop(context)),
        ],
      ),
    );
  }

  Widget _buildFooter(String? myRole, bool projectBusy) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: SupabaseColors.border)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              if (Session().isSysAdmin) ...[
                DangerButton(
                  label: 'Excluir',
                  icon: Icons.delete_outline_rounded,
                  onPressed: projectBusy ? null : _deleteProject,
                ),
                const SizedBox(width: 8),
                SecondaryButton(
                  label: 'Transferir',
                  icon: Icons.swap_horiz_rounded,
                  onPressed: projectBusy ? null : () => _showTransferDialog(),
                ),
              ],
            ],
          ),
          PrimaryButton(
            label: 'Fechar',
            onPressed: () => Navigator.pop(context),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingDialog() {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 400),
        padding: const EdgeInsets.all(40),
        decoration: BoxDecoration(
          color: SupabaseColors.bg200,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 32,
              height: 32,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SupabaseColors.brand,
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Carregando configurações...',
              style: TextStyle(
                color: SupabaseColors.textSecondary,
                fontSize: 13,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUrlSection(String projectUrl) {
    return SectionWidget(
      title: 'URL DO PROJETO',
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: SupabaseColors.bg300,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.link_rounded,
              size: 16,
              color: SupabaseColors.textMuted,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: SelectableText(
                projectUrl.isNotEmpty ? projectUrl : 'Carregando...',
                style: const TextStyle(
                  fontSize: 13,
                  fontFamily: 'monospace',
                  color: SupabaseColors.textSecondary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButtonWidget(
              icon: Icons.copy_rounded,
              tooltip: 'Copiar URL',
              onPressed: projectUrl.isNotEmpty
                  ? () {
                      Clipboard.setData(ClipboardData(text: projectUrl));
                      _showSnack('URL copiada!', SupabaseColors.success);
                    }
                  : null,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildIdentitySection(String? myRole, bool projectBusy) {
    final isAdmin = myRole == 'admin' || Session().isSysAdmin;
    final hasDisplayChange =
        _displayNameController.text.trim() != (_currentDisplayName ?? '');

    return SectionWidget(
      title: 'IDENTIDADE DO PROJETO',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SupabaseColors.bg300,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SupabaseColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Text(
                      'SLUG / PATH',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1,
                        color: SupabaseColors.textMuted,
                      ),
                    ),
                    const Spacer(),
                    TextButton.icon(
                      onPressed: () => _openHistoryDialog(),
                      icon: const Icon(Icons.history_rounded, size: 14),
                      label: const Text('Histórico'),
                      style: TextButton.styleFrom(
                        foregroundColor: SupabaseColors.textSecondary,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(
                      child: SelectableText(
                        widget.ref,
                        style: const TextStyle(
                          fontSize: 13,
                          fontFamily: 'monospace',
                          color: SupabaseColors.textPrimary,
                        ),
                      ),
                    ),
                    if (isAdmin) ...[
                      const SizedBox(width: 8),
                      SecondaryButton(
                        label: 'Renomear',
                        icon: Icons.drive_file_rename_outline_rounded,
                        onPressed: _savingDisplayName || projectBusy
                            ? null
                            : _openRenameDialog,
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SupabaseColors.bg300,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SupabaseColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'NOME DE EXIBIÇÃO',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                    color: SupabaseColors.textMuted,
                  ),
                ),
                const SizedBox(height: 6),
                TextField(
                  controller: _displayNameController,
                  enabled: isAdmin && !_savingDisplayName && !projectBusy,
                  style: const TextStyle(
                    fontSize: 13,
                    color: SupabaseColors.textPrimary,
                  ),
                  decoration: const InputDecoration(
                    isDense: true,
                    hintText: 'Nome humano do projeto',
                  ),
                  onChanged: (_) {
                    if (mounted) setState(() {});
                  },
                ),
                if (isAdmin) ...[
                  const SizedBox(height: 10),
                  Align(
                    alignment: Alignment.centerRight,
                    child: SecondaryButton(
                      onPressed:
                          !hasDisplayChange || _savingDisplayName || projectBusy
                              ? null
                              : _saveDisplayName,
                      icon: Icons.save_outlined,
                      label: _savingDisplayName
                          ? 'Salvando...'
                          : 'Salvar display name',
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAnonKeySection(String? myRole, bool projectBusy) {
    final hasKey = _currentAnonKey.isNotEmpty;
    return SectionWidget(
      title: 'CHAVE ANÔNIMA',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SupabaseColors.bg300,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SupabaseColors.border),
            ),
            child: Row(
              children: [
                Expanded(
                  child: SelectableText(
                    hasKey ? _currentAnonKey : 'Não disponível',
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textSecondary,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButtonWidget(
                  icon: Icons.copy_rounded,
                  tooltip: 'Copiar',
                  onPressed: hasKey
                      ? () {
                          Clipboard.setData(
                            ClipboardData(text: _currentAnonKey),
                          );
                          _showSnack('Chave copiada!', SupabaseColors.success);
                        }
                      : null,
                ),
              ],
            ),
          ),
          if (hasKey) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(
                  Icons.schedule_rounded,
                  size: 14,
                  color: SupabaseColors.textMuted,
                ),
                const SizedBox(width: 6),
                Text(
                  'Expira em: ${DateFormat('dd/MM/yyyy HH:mm').format(JwtDecoder.getExpirationDate(_currentAnonKey))}',
                  style: const TextStyle(
                    fontSize: 11,
                    color: SupabaseColors.textMuted,
                  ),
                ),
              ],
            ),
          ],
          if (myRole == 'admin' || Session().isSysAdmin) ...[
            const SizedBox(height: 12),
            SecondaryButton(
              label: 'Gerar nova chave',
              icon: Icons.refresh_rounded,
              onPressed: _rotatingKey || projectBusy ? null : _rotateKey,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildConfigTokenSection() {
    final hasToken = _currentConfigToken.isNotEmpty;
    return SectionWidget(
      title: 'TOKEN DE CONFIGURAÇÃO',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SupabaseColors.bg300,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SupabaseColors.border),
            ),
            child: Row(
              children: [
                Expanded(
                  child: SelectableText(
                    hasToken ? _currentConfigToken : 'Não disponível',
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textSecondary,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButtonWidget(
                  icon:
                      hasToken ? Icons.copy_rounded : Icons.visibility_outlined,
                  tooltip: hasToken ? 'Copiar' : 'Carregar token',
                  onPressed: hasToken
                      ? () {
                          Clipboard.setData(
                            ClipboardData(text: _currentConfigToken),
                          );
                          _showSnack('Token copiado!', SupabaseColors.success);
                        }
                      : (_loadingConfigToken ? null : _loadConfigToken),
                ),
              ],
            ),
          ),
          if (hasToken) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(
                  Icons.info_outline,
                  size: 14,
                  color: SupabaseColors.textMuted,
                ),
                const SizedBox(width: 6),
                const Expanded(
                  child: Text(
                    'Use este token no header X-Config-Token para acessar o endpoint /config',
                    style: TextStyle(
                      fontSize: 11,
                      color: SupabaseColors.textMuted,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  void _showTransferDialog() {
    showDialog(
      context: context,
      builder: (ctx) => TransferProjectDialog(
        projectName: widget.ref,
        onTransfer: (newOwnerId) async {
          try {
            await ref
                .read(projectRepositoryProvider)
                .transferProject(widget.ref, newOwnerId);

            ref.invalidate(projectMembersProvider(widget.ref));
            ref.invalidate(availableUsersProvider(widget.ref));

            if (mounted) {
              _showSnack(
                'Projeto "${widget.ref}" transferido com sucesso!',
                SupabaseColors.success,
              );
            }
          } catch (e) {
            final msg = e.toString().replaceFirst('Exception: ', '');
            if (mounted) {
              _showSnack(
                'Erro ao transferir projeto: $msg',
                SupabaseColors.error,
              );
            }
          }
        },
        loadAvailableUsers: (projectName) async {
          final users = await ref
              .read(projectRepositoryProvider)
              .getTransferAvailableUsers(projectName);
          return users.map((u) => AvailableUser.fromJson(u)).toList();
        },
      ),
    );
  }
}
