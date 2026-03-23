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
import 'services/projectService.dart';
import 'dialogs/transferProjectDialog.dart';

import 'widgets/close_button_widget.dart';
import 'widgets/icon_button_widget.dart';
import 'widgets/primary_button.dart';
import 'widgets/secondary_button.dart';
import 'widgets/danger_button.dart';
import 'widgets/section_widget.dart';
import 'widgets/project_settings/status_section.dart';
import 'widgets/project_settings/members_section.dart';
import 'models/project_member.dart';
import 'models/AllUsers.dart';

class ProjectSettingsDialog extends ConsumerStatefulWidget {
  const ProjectSettingsDialog({
    super.key,
    required this.ref,
    required this.anonKey,
    required this.configToken,
  });

  final String ref;
  final String anonKey;
  final String configToken;

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
  bool _rotatingKey = false;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
        duration: const Duration(milliseconds: 300), vsync: this);
    _fadeAnimation =
        CurvedAnimation(parent: _animController, curve: Curves.easeOut);
    _animController.forward();

    _currentAnonKey = widget.anonKey;
    _currentConfigToken = widget.configToken;
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
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
            side: const BorderSide(color: SupabaseColors.border)),
        title: const Row(children: [
          Icon(Icons.warning_rounded, color: SupabaseColors.warning),
          SizedBox(width: 8),
          Text('Gerar nova chave?',
              style: TextStyle(color: SupabaseColors.textPrimary)),
        ]),
        content: const Text(
          'A chave atual será invalidada. Apps usando ela vão parar de funcionar até serem atualizados.',
          style: TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style:
                TextButton.styleFrom(foregroundColor: SupabaseColors.warning),
            child: const Text('Gerar'),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    setState(() => _rotatingKey = true);
    try {
      final data =
          await ref.read(projectRepositoryProvider).rotateKey(widget.ref);
      setState(() => _currentAnonKey = data['anon_key']);
      await ref.read(projectRepositoryProvider).cacheBust(widget.ref);
      _showSnack('Nova chave gerada!', SupabaseColors.success);
    } catch (e) {
      _showSnack('Erro ao gerar chave: $e', SupabaseColors.error);
    } finally {
      if (mounted) setState(() => _rotatingKey = false);
    }
  }

  Future<void> _deleteProject() async {
    bool sucesso =
        await ProjectService.confirmAndDeleteProject(context, widget.ref);
    if (sucesso && mounted) Navigator.of(context).pop(widget.ref);
  }


  @override
  Widget build(BuildContext context) {
    final configAsync = ref.watch(configProvider);
    final serverDomain = configAsync.value?['server_domain'] as String? ?? '';
    final projectUrl =
        serverDomain.isNotEmpty ? '$serverDomain/${widget.ref}' : widget.ref;

    final membersAsync = ref.watch(projectMembersProvider(widget.ref));
    final myId = Session().myId;
    final myRole = membersAsync.value
        ?.firstWhere((m) => m.user_id == myId,
            orElse: () => ProjectMember(user_id: '', role: 'member'))
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
                      _buildAnonKeySection(myRole),
                      const SizedBox(height: 20),
                      _buildConfigTokenSection(),
                      const SizedBox(height: 20),
                      MembersSection(projectRef: widget.ref),
                    ],
                  ),
                ),
              ),
              _buildFooter(myRole),
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
              color: SupabaseColors.brand.withValues(alpha:0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(Icons.settings_rounded,
                color: SupabaseColors.brand, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Configurações',
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 0.5,
                        color: SupabaseColors.textMuted)),
                const SizedBox(height: 2),
                Text(widget.ref,
                    style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                        color: SupabaseColors.textPrimary)),
              ],
            ),
          ),
          CloseButtonWidget(onPressed: () => Navigator.pop(context)),
        ],
      ),
    );
  }

  Widget _buildFooter(String? myRole) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: SupabaseColors.border))),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              if (Session().isSysAdmin) ...[
                DangerButton(
                    label: 'Excluir',
                    icon: Icons.delete_outline_rounded,
                    onPressed: _deleteProject),
                const SizedBox(width: 8),
                SecondaryButton(
                  label: 'Transferir',
                  icon: Icons.swap_horiz_rounded,
                  onPressed: () => _showTransferDialog(),
                ),
              ],
            ],
          ),
          PrimaryButton(
              label: 'Fechar', onPressed: () => Navigator.pop(context)),
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
            border: Border.all(color: SupabaseColors.border)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
                width: 32,
                height: 32,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: SupabaseColors.brand)),
            const SizedBox(height: 16),
            const Text('Carregando configurações...',
                style: TextStyle(
                    color: SupabaseColors.textSecondary, fontSize: 13)),
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
            border: Border.all(color: SupabaseColors.border)),
        child: Row(
          children: [
            const Icon(Icons.link_rounded,
                size: 16, color: SupabaseColors.textMuted),
            const SizedBox(width: 10),
            Expanded(
                child: SelectableText(
                    projectUrl.isNotEmpty ? projectUrl : 'Carregando...',
                    style: const TextStyle(
                        fontSize: 13,
                        fontFamily: 'monospace',
                        color: SupabaseColors.textSecondary))),
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

  Widget _buildAnonKeySection(String? myRole) {
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
                border: Border.all(color: SupabaseColors.border)),
            child: Row(
              children: [
                Expanded(
                    child: SelectableText(
                        hasKey ? _currentAnonKey : 'Não disponível',
                        style: const TextStyle(
                            fontSize: 12,
                            fontFamily: 'monospace',
                            color: SupabaseColors.textSecondary))),
                const SizedBox(width: 8),
                IconButtonWidget(
                  icon: Icons.copy_rounded,
                  tooltip: 'Copiar',
                  onPressed: hasKey
                      ? () {
                          Clipboard.setData(
                              ClipboardData(text: _currentAnonKey));
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
                const Icon(Icons.schedule_rounded,
                    size: 14, color: SupabaseColors.textMuted),
                const SizedBox(width: 6),
                Text(
                    'Expira em: ${DateFormat('dd/MM/yyyy HH:mm').format(JwtDecoder.getExpirationDate(_currentAnonKey))}',
                    style: const TextStyle(
                        fontSize: 11, color: SupabaseColors.textMuted)),
              ],
            ),
          ],
          if (myRole == 'admin') ...[
            const SizedBox(height: 12),
            SecondaryButton(
                label: 'Gerar nova chave',
                icon: Icons.refresh_rounded,
                onPressed: _rotatingKey ? null : _rotateKey),
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
                border: Border.all(color: SupabaseColors.border)),
            child: Row(
              children: [
                Expanded(
                    child: SelectableText(
                        hasToken ? _currentConfigToken : 'Não disponível',
                        style: const TextStyle(
                            fontSize: 12,
                            fontFamily: 'monospace',
                            color: SupabaseColors.textSecondary))),
                const SizedBox(width: 8),
                IconButtonWidget(
                  icon: Icons.copy_rounded,
                  tooltip: 'Copiar',
                  onPressed: hasToken
                      ? () {
                          Clipboard.setData(
                              ClipboardData(text: _currentConfigToken));
                          _showSnack('Token copiado!', SupabaseColors.success);
                        }
                      : null,
                ),
              ],
            ),
          ),
          if (hasToken) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.info_outline,
                    size: 14, color: SupabaseColors.textMuted),
                const SizedBox(width: 6),
                const Expanded(
                    child: Text(
                        'Use este token no header X-Config-Token para acessar o endpoint /config',
                        style: TextStyle(
                            fontSize: 11, color: SupabaseColors.textMuted))),
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
            await ref.read(projectRepositoryProvider).transferProject(widget.ref, newOwnerId);
            if (mounted) _showSnack('Projeto "${widget.ref}" transferido com sucesso!', SupabaseColors.success);
          } catch(e) {
            final msg = e.toString().replaceFirst('Exception: ', '');
            if (mounted) _showSnack('Erro ao transferir projeto: $msg', SupabaseColors.error);
          }
        },
        loadAvailableUsers: (projectName) async {
          final users = await ref
              .read(projectRepositoryProvider)
              .getAvailableUsers(projectName);
          return users.map((u) => AvailableUser.fromJson(u)).toList();
        },
      ),
    );
  }
}
