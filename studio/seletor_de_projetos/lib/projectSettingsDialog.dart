import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';
import 'package:jwt_decoder/jwt_decoder.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';
import 'dialogs/addMemberDialog.dart';
import 'dialogs/transferProjectDialog.dart';
import 'models/AllUsers.dart';
import 'models/projectDockerStatus.dart';

class ProjectSettingsDialog extends StatefulWidget {
  const ProjectSettingsDialog({
    super.key,
    required this.ref,
    required this.anonKey,
  });

  final String ref;
  final String anonKey;

  @override
  State<ProjectSettingsDialog> createState() => _ProjectSettingsDialogState();
}

class _ProjectSettingsDialogState extends State<ProjectSettingsDialog>
    with SingleTickerProviderStateMixin {
  List<ProjectMember> _currentMembers = [];
  List<AvailableUserShort> _availableUsers = [];
  bool _loadingMembers = true;
  bool _loadingAvailable = false;
  bool _addingMember = false;
  String? _error;
  String? _myProjectRole;
  ProjectDockerStatus? _status;
  bool _statusLoading = true;
  String? _statusError;
  late bool _busy;
  late AnimationController _animController;
  late Animation<double> _fadeAnimation;
  String _projectUrl = '';

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

    _busy = Session().isBusy(widget.ref);
    Session().busyListenable.addListener(_onBusyChanged);

    _loadCurrentMembers();
    _loadStatus();
    _loadProjectUrl();

    _animController.forward();
  }

  @override
  void dispose() {
    Session().busyListenable.removeListener(_onBusyChanged);
    _animController.dispose();
    super.dispose();
  }

  void _onBusyChanged() {
    if (!mounted) return;
    final b = Session().isBusy(widget.ref);
    if (b != _busy) {
      setState(() => _busy = b);
      if (!b) _loadStatus();
    }
  }

  void _safeSetState(VoidCallback fn) {
    if (mounted) setState(fn);
  }

  Future<void> _loadCurrentMembers() async {
    _safeSetState(() {
      _loadingMembers = true;
      _error = null;
    });

    try {
      final response = await http.get(
        Uri.parse('/api/projects/${widget.ref}/members'),
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        _safeSetState(() {
          _currentMembers = data.map((item) => ProjectMember.fromJson(item)).toList();
          final session = Session();
          final me = _currentMembers.firstWhere(
                (m) => m.user_id == session.myId,
            orElse: () => ProjectMember(user_id: '', role: 'member'),
          );
          _myProjectRole = me.role;
          _loadingMembers = false;
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      setState(() {
        _error = 'Erro ao carregar membros: $e';
        _loadingMembers = false;
      });
    }
  }

  Future<void> _loadAvailableUsersForProject() async {
    _safeSetState(() {
      _loadingAvailable = true;
      _error = null;
    });

    try {
      final response = await http.get(
        Uri.parse('/api/projects/${widget.ref}/available-users'),
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        _safeSetState(() {
          _availableUsers = data.map((item) => AvailableUserShort.fromJson(item)).toList();
          _loadingAvailable = false;
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _safeSetState(() {
        // _error = 'Erro ao carregar usuários disponíveis: $e';
        _loadingAvailable = false;
      });
    }
  }

  Future<void> _addMember(String userId, String role) async {
    _safeSetState(() => _addingMember = true);

    try {
      final response = await http.post(
        Uri.parse('/api/projects/${widget.ref}/members'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'user_id': userId, 'role': role}),
      );

      if (response.statusCode == 200) {
        _showSnack('Membro adicionado com sucesso!', SupabaseColors.success);
        await _loadCurrentMembers();
        _safeSetState(() {
          _availableUsers.removeWhere((user) => user.userId == userId);
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _showSnack('Erro ao adicionar membro: $e', SupabaseColors.error);
    } finally {
      _safeSetState(() => _addingMember = false);
    }
  }

  Future<void> _removeMember(String userId) async {
    try {
      final response = await http.delete(
        Uri.parse('/api/projects/${widget.ref}/members/$userId'),
      );

      if (response.statusCode == 200) {
        _showSnack('Membro removido com sucesso!', SupabaseColors.success);
        await _loadCurrentMembers();
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _showSnack('Erro ao remover membro: $e', SupabaseColors.error);
    }
  }

  void _showSnack(String msg, Color color) {
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

  void _openAddMemberDialog() {
    showDialog(
      context: context,
      barrierDismissible: !_addingMember,
      builder: (_) => AddMemberDialog(
        loadUsers: _loadAvailableUsersForProject,
        getUsers: () => _availableUsers,
        onAdd: _addMember,
      ),
    ).then((_) => _loadCurrentMembers());
  }

  Future<void> _loadStatus() async {
    _safeSetState(() {
      _statusLoading = true;
      _statusError = null;
    });

    try {
      final resp = await http.get(
        Uri.parse('/api/projects/${widget.ref}/status'),
      );

      if (resp.statusCode == 200) {
        final data = ProjectDockerStatus.fromJson(jsonDecode(resp.body));
        _safeSetState(() {
          _status = data;
          _statusLoading = false;
        });
      } else {
        throw Exception('Erro ${resp.statusCode}: ${resp.body}');
      }
    } catch (e) {
      _safeSetState(() {
        _statusError = 'Erro ao obter status: $e';
        _statusLoading = false;
      });
    }
  }

  Future<void> _loadProjectUrl() async {
    try {
      final resp = await http.get(Uri.parse('/api/config'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        final serverDomain = data['server_domain'] ?? '';
        _safeSetState(() {
          _projectUrl = serverDomain.isNotEmpty
              ? '$serverDomain/${widget.ref}'
              : widget.ref;
        });
      }
    } catch (_) {
      _safeSetState(() => _projectUrl = widget.ref);
    }
  }

  Future<void> _doAction(String action) async {
    final tracker = Session();
    if (tracker.isBusy(widget.ref)) return;

    tracker.setBusy(widget.ref, true);
    try {
      final resp = await http.post(
        Uri.parse('/api/projects/${widget.ref}/$action'),
      );
      if (!mounted) return;

      if (resp.statusCode == 200) {
        _showSnack('Ação $action executada', SupabaseColors.success);
        await _loadStatus();
      } else {
        final err = jsonDecode(resp.body)['detail'] ?? resp.body;
        _showSnack('Falha: $err', SupabaseColors.error);
      }
    } catch (e) {
      if (mounted) _showSnack('Erro: $e', SupabaseColors.error);
    } finally {
      tracker.setBusy(widget.ref, false);
    }
  }

  Future<void> _deleteProject() async {
    bool sucesso = await ProjectService.confirmAndDeleteProject(context, widget.ref);
    if (sucesso) Navigator.of(context).pop(widget.ref);
  }

  @override
  Widget build(BuildContext context) {
    final session = Session();

    if (_myProjectRole == null) {
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
              Container(
                padding: const EdgeInsets.all(20),
                decoration: const BoxDecoration(
                  border: Border(
                    bottom: BorderSide(color: SupabaseColors.border),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: SupabaseColors.brand.withOpacity(0.15),
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
                    _CloseButton(onPressed: () => Navigator.pop(context)),
                  ],
                ),
              ),

              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildStatusSection(),
                      const SizedBox(height: 20),
                      _buildProjectUrlSection(),
                      const SizedBox(height: 20),
                      _buildAnonKeySection(),
                      const SizedBox(height: 20),
                      _buildMembersSection(),
                    ],
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: const BoxDecoration(
                  border: Border(
                    top: BorderSide(color: SupabaseColors.border),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        if (session.isSysAdmin) ...[
                          _DangerButton(
                            label: 'Excluir',
                            icon: Icons.delete_outline_rounded,
                            onPressed: _deleteProject,
                          ),
                          const SizedBox(width: 8),
                          _SecondaryButton(
                            label: 'Transferir',
                            icon: Icons.swap_horiz_rounded,
                            onPressed: () => _showTransferDialog(widget.ref),
                          ),
                        ],
                      ],
                    ),
                    _PrimaryButton(
                      label: 'Fechar',
                      onPressed: () => Navigator.pop(context),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
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
            SizedBox(
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

  Widget _buildProjectUrlSection() {
    return _Section(
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
                _projectUrl.isNotEmpty ? _projectUrl : 'Carregando...',
                style: const TextStyle(
                  fontSize: 13,
                  fontFamily: 'monospace',
                  color: SupabaseColors.textSecondary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            _IconBtn(
              icon: Icons.copy_rounded,
              tooltip: 'Copiar URL',
              onPressed: _projectUrl.isNotEmpty
                  ? () {
                Clipboard.setData(ClipboardData(text: _projectUrl));
                _showSnack('URL copiada!', SupabaseColors.success);
              }
                  : null,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusSection() {
    return _Section(
      title: 'STATUS',
      child: _statusLoading
          ? const Center(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
          ),
        ),
      )
          : _statusError != null
          ? _ErrorBox(message: _statusError!)
          : _status == null
          ? const SizedBox.shrink()
          : _buildStatusContent(),
    );
  }

  Widget _buildStatusContent() {
    final st = _status!;
    final isRunning = st.status == 'running';
    final busy = Session().isBusy(widget.ref);

    return Column(
      children: [
        Row(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isRunning ? SupabaseColors.success : SupabaseColors.error,
                boxShadow: [
                  BoxShadow(
                    color: (isRunning ? SupabaseColors.success : SupabaseColors.error)
                        .withOpacity(0.5),
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
                      color: isRunning ? SupabaseColors.success : SupabaseColors.error,
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
        if (_myProjectRole == 'admin') ...[
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _ActionButton(
                  icon: Icons.play_arrow_rounded,
                  label: 'Start',
                  color: SupabaseColors.success,
                  onPressed: busy ? null : () => _doAction('start'),
                  busy: busy,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _ActionButton(
                  icon: Icons.stop_rounded,
                  label: 'Stop',
                  color: SupabaseColors.error,
                  onPressed: busy ? null : () => _doAction('stop'),
                  busy: busy,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _ActionButton(
                  icon: Icons.restart_alt_rounded,
                  label: 'Restart',
                  color: SupabaseColors.info,
                  onPressed: busy ? null : () => _doAction('restart'),
                  busy: busy,
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }


  Widget _buildAnonKeySection() {
    final hasKey = widget.anonKey.isNotEmpty;

    return _Section(
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
                    hasKey ? widget.anonKey : 'Não disponível',
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textSecondary,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                _IconBtn(
                  icon: Icons.copy_rounded,
                  tooltip: 'Copiar',
                  onPressed: hasKey
                      ? () {
                    Clipboard.setData(ClipboardData(text: widget.anonKey));
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
                const Icon(Icons.schedule_rounded, size: 14, color: SupabaseColors.textMuted),
                const SizedBox(width: 6),
                Text(
                  'Expira em: ${DateFormat('dd/MM/yyyy HH:mm').format(JwtDecoder.getExpirationDate(widget.anonKey))}',
                  style: const TextStyle(fontSize: 11, color: SupabaseColors.textMuted),
                ),
              ],
            ),
          ],
          if (_myProjectRole == 'admin') ...[
            const SizedBox(height: 12),
            _SecondaryButton(
              label: 'Gerar nova chave',
              icon: Icons.refresh_rounded,
              onPressed: null, // TODO: implement
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMembersSection() {
    return _Section(
      title: 'MEMBROS',
      trailing: _myProjectRole == 'admin'
          ? _SecondaryButton(
        label: 'Adicionar',
        icon: Icons.person_add_rounded,
        onPressed: _loadingMembers ? null : _openAddMemberDialog,
      )
          : null,
      child: _loadingMembers
          ? const Center(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
          ),
        ),
      )
          : _error != null
          ? _ErrorBox(message: _error!, onRetry: _loadCurrentMembers)
          : _currentMembers.isEmpty
          ? const Center(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Text(
            'Nenhum membro encontrado',
            style: TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
          ),
        ),
      )
          : _buildMembersList(),
    );
  }

  Widget _buildMembersList() {
    return Column(
      children: _currentMembers.map((member) {
        final session = Session();
        final isMe = member.user_id == session.myId;
        final canRemove = _myProjectRole == 'admin' && member.role != 'admin' && !isMe;

        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: isMe ? SupabaseColors.brand.withOpacity(0.1) : SupabaseColors.bg300,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: isMe ? SupabaseColors.brand.withOpacity(0.3) : SupabaseColors.border,
            ),
          ),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: member.role == 'admin'
                      ? SupabaseColors.warning.withOpacity(0.2)
                      : SupabaseColors.info.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Icon(
                  member.role == 'admin'
                      ? Icons.admin_panel_settings_rounded
                      : Icons.person_rounded,
                  color: member.role == 'admin' ? SupabaseColors.warning : SupabaseColors.info,
                  size: 18,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isMe ? '${member.displayName ?? 'Você'} (você)' : member.displayName ?? 'Sem nome',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: isMe ? FontWeight.w600 : FontWeight.w500,
                        color: SupabaseColors.textPrimary,
                      ),
                    ),
                    Text(
                      member.role == 'admin' ? 'Administrador' : 'Membro',
                      style: const TextStyle(fontSize: 11, color: SupabaseColors.textMuted),
                    ),
                  ],
                ),
              ),
              if (canRemove)
                _IconBtn(
                  icon: Icons.remove_circle_outline_rounded,
                  tooltip: 'Remover',
                  color: SupabaseColors.error,
                  onPressed: () => _showRemoveConfirmation(member),
                ),
            ],
          ),
        );
      }).toList(),
    );
  }

  void _showRemoveConfirmation(ProjectMember member) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: SupabaseColors.bg200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: SupabaseColors.error.withOpacity(0.15),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Icon(Icons.warning_rounded, color: SupabaseColors.error, size: 20),
            ),
            const SizedBox(width: 12),
            const Text('Confirmar Remoção', style: TextStyle(color: SupabaseColors.textPrimary)),
          ],
        ),
        content: Text(
          'Tem certeza que deseja remover ${member.displayName ?? 'este usuário'} do projeto?',
          style: const TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          _DangerButton(
            label: 'Remover',
            onPressed: () {
              Navigator.pop(context);
              _removeMember(member.user_id);
            },
          ),
        ],
      ),
    );
  }

  Future<List<AvailableUser>> _loadAvailableUsers(String projectName) async {
    try {
      final response = await http.get(
        Uri.parse('/api/admin/projects/$projectName/all-users'),
      );

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        final dynamic usersData = data['users'];
        if (usersData == null || usersData is! List) return <AvailableUser>[];
        final List<dynamic> usersJson = usersData;
        return usersJson
            .map((item) => AvailableUser.fromJson(item))
            .where((user) => user.userId != widget.ref)
            .toList();
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      throw Exception('Erro ao carregar usuários disponíveis: $e');
    }
  }

  Future<void> _transferProject(String projectName, String newOwnerId) async {
    try {
      final response = await http.post(
        Uri.parse('/api/admin/projects/$projectName/transfer'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'new_owner_id': newOwnerId}),
      );

      if (response.statusCode == 200) {
        _showSnack('Projeto "$projectName" transferido com sucesso!', SupabaseColors.success);
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _showSnack('Erro ao transferir projeto: $e', SupabaseColors.error);
    }
  }

  void _showTransferDialog(String projectName) {
    showDialog(
      context: context,
      builder: (context) => TransferProjectDialog(
        projectName: projectName,
        onTransfer: (newOwnerId) => _transferProject(projectName, newOwnerId),
        loadAvailableUsers: _loadAvailableUsers,
      ),
    );
  }
}


class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child, this.trailing});

  final String title;
  final Widget child;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1,
                    color: SupabaseColors.textMuted,
                  ),
                ),
                if (trailing != null) trailing!,
              ],
            ),
          ),
          const Divider(color: SupabaseColors.border, height: 1),
          Padding(padding: const EdgeInsets.all(16), child: child),
        ],
      ),
    );
  }
}

class _ErrorBox extends StatelessWidget {
  const _ErrorBox({required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.error.withOpacity(0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.error.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: SupabaseColors.error, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: const TextStyle(color: SupabaseColors.error, fontSize: 12)),
          ),
          if (onRetry != null)
            TextButton(
              onPressed: onRetry,
              child: const Text('Tentar novamente', style: TextStyle(fontSize: 12)),
            ),
        ],
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  const _IconBtn({required this.icon, required this.tooltip, this.onPressed, this.color});

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(4),
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Icon(
              icon,
              size: 16,
              color: onPressed == null
                  ? SupabaseColors.textMuted.withOpacity(0.5)
                  : (color ?? SupabaseColors.textSecondary),
            ),
          ),
        ),
      ),
    );
  }
}

class _CloseButton extends StatelessWidget {
  const _CloseButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(4),
        child: const Padding(
          padding: EdgeInsets.all(6),
          child: Icon(Icons.close_rounded, size: 18, color: SupabaseColors.textMuted),
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.color,
    this.onPressed,
    this.busy = false,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: onPressed == null ? SupabaseColors.bg300 : color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: onPressed == null ? SupabaseColors.border : color.withOpacity(0.3),
            ),
          ),
          child: Column(
            children: [
              if (busy)
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(color)),
                )
              else
                Icon(icon, color: onPressed == null ? SupabaseColors.textMuted : color, size: 18),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                  color: onPressed == null ? SupabaseColors.textMuted : color,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        backgroundColor: SupabaseColors.brand,
        foregroundColor: SupabaseColors.bg100,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
      child: Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
    );
  }
}

class _SecondaryButton extends StatelessWidget {
  const _SecondaryButton({required this.label, this.icon, this.onPressed});

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        backgroundColor: SupabaseColors.surface200,
        foregroundColor: SupabaseColors.textPrimary,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(6),
          side: const BorderSide(color: SupabaseColors.border),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14),
            const SizedBox(width: 6),
          ],
          Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

class _DangerButton extends StatelessWidget {
  const _DangerButton({required this.label, this.icon, required this.onPressed});

  final String label;
  final IconData? icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        foregroundColor: SupabaseColors.error,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14),
            const SizedBox(width: 6),
          ],
          Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

class ProjectMember {
  final String user_id;
  final String role;
  final String? displayName;

  ProjectMember({required this.user_id, required this.role, this.displayName});

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    return ProjectMember(
      user_id: json['user_id'] as String,
      displayName: json['display_name'] as String?,
      role: json['role'] as String,
    );
  }
}