import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';
import 'package:jwt_decoder/jwt_decoder.dart';
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

class _ProjectSettingsDialogState extends State<ProjectSettingsDialog> with SingleTickerProviderStateMixin {
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

  @override
  void initState() {
    super.initState();

    // Inicializa animações primeiro
    _animController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animController,
      curve: Curves.easeOut,
    );

    // Inicializa busy
    _busy = Session().isBusy(widget.ref);
    Session().busyListenable.addListener(_onBusyChanged);

    // Carrega dados (async)
    _loadCurrentMembers();
    _loadStatus();

    // Inicia animação
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
      if (!b) {
        _loadStatus();
      }
    }
  }

  void _safeSetState(VoidCallback fn) {
    if (mounted) {
      setState(fn);
    }
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
          _currentMembers = data
              .map((item) => ProjectMember.fromJson(item))
              .toList();
          final session = Session();
          final me = _currentMembers.firstWhere(
                  (m) => m.user_id == session.myId,
              orElse: () => ProjectMember(user_id: '', role: 'member'));

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
          _availableUsers = data
              .map((item) => AvailableUserShort.fromJson(item))
              .toList();
          _loadingAvailable = false;
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _safeSetState(() {
        _error = 'Erro ao carregar usuários disponíveis: $e';
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
        body: jsonEncode({
          'user_id': userId,
          'role': role,
        }),
      );

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Membro adicionado com sucesso!'),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.all(16),
          ),
        );
        await _loadCurrentMembers();
        _safeSetState(() {
          _availableUsers.removeWhere((user) => user.userId == userId);
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Erro ao adicionar membro: $e'),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Colors.red,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ),
      );
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
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Membro removido com sucesso!'),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.all(16),
          ),
        );
        await _loadCurrentMembers();
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Erro ao remover membro: $e'),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Colors.red,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ),
      );
    }
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

  Widget _buildStatusCard() {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    if (_statusLoading) {
      return Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: isDark
                ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
                : [Colors.white, Colors.grey[50]!],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08),
          ),
        ),
        child: const Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }

    if (_statusError != null) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [Colors.red.shade50, Colors.red.shade100],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.red.shade200),
        ),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: Colors.red.shade700),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                _statusError!,
                style: TextStyle(color: Colors.red.shade900),
              ),
            ),
          ],
        ),
      );
    }

    if (_status == null) {
      return const SizedBox.shrink();
    }

    final st = _status!;
    final isRunning = st.status == 'running';
    final busy = Session().isBusy(widget.ref);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isDark
              ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
              : [Colors.white, Colors.grey[50]!],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isRunning
              ? Colors.green.withOpacity(0.3)
              : Colors.orange.withOpacity(0.3),
          width: 1.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isRunning
                      ? Colors.green.withOpacity(0.15)
                      : Colors.orange.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  isRunning ? Icons.check_circle_rounded : Icons.warning_rounded,
                  color: isRunning ? Colors.green : Colors.orange,
                  size: 24,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Status do Projeto',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.2,
                        color: isDark ? Colors.white38 : Colors.black38,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      st.status.toUpperCase(),
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: isRunning ? Colors.green : Colors.orange,
                        letterSpacing: -0.5,
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: isDark
                      ? Colors.white.withOpacity(0.05)
                      : Colors.black.withOpacity(0.03),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '${st.running}/${st.total}',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: isDark ? Colors.white70 : Colors.black87,
                  ),
                ),
              ),
            ],
          ),
          if (_myProjectRole == 'admin') ...[
            const SizedBox(height: 16),
            Divider(color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08)),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: _buildActionButton(
                    icon: Icons.play_arrow_rounded,
                    label: 'Start',
                    color: Colors.green,
                    onPressed: busy ? null : () => _doAction('start'),
                    busy: busy,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _buildActionButton(
                    icon: Icons.stop_rounded,
                    label: 'Stop',
                    color: Colors.red,
                    onPressed: busy ? null : () => _doAction('stop'),
                    busy: busy,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _buildActionButton(
                    icon: Icons.restart_alt_rounded,
                    label: 'Restart',
                    color: Colors.blue,
                    onPressed: busy ? null : () => _doAction('restart'),
                    busy: busy,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback? onPressed,
    bool busy = false,
  }) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: onPressed == null
                ? (isDark ? Colors.white.withOpacity(0.03) : Colors.grey[200])
                : color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: onPressed == null
                  ? (isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.08))
                  : color.withOpacity(0.3),
            ),
          ),
          child: Column(
            children: [
              if (busy)
                SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(color),
                  ),
                )
              else
                Icon(icon, color: onPressed == null ? Colors.grey : color, size: 20),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: onPressed == null ? Colors.grey : color,
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Ação $action executada'),
          backgroundColor: Colors.green,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ));
        await _loadStatus();
      } else {
        final err = jsonDecode(resp.body)['detail'] ?? resp.body;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Falha: $err'),
          backgroundColor: Colors.red,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Erro: $e'),
          backgroundColor: Colors.red,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ));
      }
    } finally {
      tracker.setBusy(widget.ref, false);
    }
  }

  Future<void> _deleteProject() async {
    bool sucesso = await ProjectService.confirmAndDeleteProject(context, widget.ref);

    if (sucesso) {
      Navigator.of(context).pop(widget.ref);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;
    final session = Session();

    // Aguarda inicialização antes de mostrar conteúdo
    if (_myProjectRole == null) {
      return Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          constraints: const BoxConstraints(maxWidth: 800),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: isDark
                  ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
                  : [Colors.white, Colors.grey[50]!],
            ),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: isDark ? Colors.white.withOpacity(0.1) : Colors.black.withOpacity(0.08),
            ),
          ),
          padding: const EdgeInsets.all(80),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 40,
                  height: 40,
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    color: t.colorScheme.primary,
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'Carregando configurações...',
                  style: TextStyle(
                    color: isDark ? Colors.white70 : Colors.black54,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Dialog(
      backgroundColor: Colors.transparent,
      child: FadeTransition(
        opacity: _fadeAnimation,
        child: Container(
          constraints: BoxConstraints(
            maxWidth: 800,
            maxHeight: MediaQuery.of(context).size.height * 0.9,
          ),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: isDark
                  ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
                  : [Colors.white, Colors.grey[50]!],
            ),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: isDark ? Colors.white.withOpacity(0.1) : Colors.black.withOpacity(0.08),
            ),
            boxShadow: [
              BoxShadow(
                color: isDark ? Colors.black.withOpacity(0.5) : Colors.black.withOpacity(0.15),
                blurRadius: 40,
                offset: const Offset(0, 20),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(32),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08),
                    ),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [t.colorScheme.primary, t.colorScheme.secondary],
                        ),
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: t.colorScheme.primary.withOpacity(0.3),
                            blurRadius: 16,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: const Icon(Icons.settings_rounded, color: Colors.white, size: 28),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Configurações',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 1.2,
                              color: isDark ? Colors.white38 : Colors.black38,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            widget.ref,
                            style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              color: isDark ? Colors.white : Colors.black87,
                              letterSpacing: -0.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: Icon(
                        Icons.close_rounded,
                        color: isDark ? Colors.white70 : Colors.black54,
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildStatusCard(),
                      const SizedBox(height: 24),
                      _buildAnonKeyCard(),
                      const SizedBox(height: 24),
                      _buildMembersSection(),
                    ],
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  border: Border(
                    top: BorderSide(
                      color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08),
                    ),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        if (session.isSysAdmin) ...[
                          TextButton.icon(
                            onPressed: () => _deleteProject(),
                            icon: const Icon(Icons.delete_outline_rounded, size: 18),
                            label: const Text('Excluir'),
                            style: TextButton.styleFrom(
                              foregroundColor: Colors.red,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            ),
                          ),
                          const SizedBox(width: 8),
                          TextButton.icon(
                            onPressed: () => _showTransferDialog(widget.ref),
                            icon: const Icon(Icons.swap_horiz_rounded, size: 18),
                            label: const Text('Transferir'),
                            style: TextButton.styleFrom(
                              foregroundColor: Colors.blue,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            ),
                          ),
                        ],
                      ],
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(context),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: const Text('Fechar'),
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

  Widget _buildAnonKeyCard() {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;
    final hasKey = widget.anonKey.isNotEmpty;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isDark
              ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
              : [Colors.white, Colors.grey[50]!],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      t.colorScheme.primary.withOpacity(0.2),
                      t.colorScheme.secondary.withOpacity(0.2),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  Icons.key_rounded,
                  color: t.colorScheme.primary,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'CHAVE ANÔNIMA',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                  color: isDark ? Colors.white38 : Colors.black38,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isDark ? Colors.black.withOpacity(0.3) : Colors.grey[100],
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.05),
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: SelectableText(
                    hasKey ? widget.anonKey : 'Não disponível',
                    style: TextStyle(
                      fontSize: 13,
                      fontFamily: 'monospace',
                      color: isDark ? Colors.white70 : Colors.black87,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                IconButton(
                  tooltip: 'Copiar chave',
                  icon: Icon(
                    Icons.copy_all_rounded,
                    size: 18,
                    color: hasKey
                        ? t.colorScheme.primary
                        : (isDark ? Colors.white24 : Colors.black26),
                  ),
                  onPressed: hasKey
                      ? () {
                    Clipboard.setData(ClipboardData(text: widget.anonKey));
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: const Text('Chave copiada'),
                        behavior: SnackBarBehavior.floating,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        margin: const EdgeInsets.all(16),
                      ),
                    );
                  }
                      : null,
                ),
              ],
            ),
          ),
          if (hasKey) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(
                  Icons.access_time_rounded,
                  size: 16,
                  color: isDark ? Colors.white38 : Colors.black38,
                ),
                const SizedBox(width: 8),
                Text(
                  'Expira em: ${DateFormat('dd/MM/yyyy HH:mm').format(JwtDecoder.getExpirationDate(widget.anonKey))}',
                  style: TextStyle(
                    fontSize: 12,
                    color: isDark ? Colors.white54 : Colors.black54,
                  ),
                ),
              ],
            ),
          ],
          if (_myProjectRole == 'admin') ...[
            const SizedBox(height: 16),
            FilledButton.tonalIcon(
              onPressed: null,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Gerar nova chave'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMembersSection() {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        t.colorScheme.primary.withOpacity(0.2),
                        t.colorScheme.secondary.withOpacity(0.2),
                      ],
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    Icons.people_rounded,
                    color: t.colorScheme.primary,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'MEMBROS DO PROJETO',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.2,
                        color: isDark ? Colors.white38 : Colors.black38,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${_currentMembers.length} ${_currentMembers.length == 1 ? 'membro' : 'membros'}',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: isDark ? Colors.white : Colors.black87,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            if (_myProjectRole == 'admin')
              FilledButton.tonalIcon(
                onPressed: _loadingMembers ? null : _openAddMemberDialog,
                icon: const Icon(Icons.person_add_rounded, size: 18),
                label: const Text('Adicionar'),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 16),
        Container(
          constraints: const BoxConstraints(maxHeight: 300),
          child: _buildMembersList(),
        ),
      ],
    );
  }

  Widget _buildMembersList() {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    if (_loadingMembers) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(
              width: 32,
              height: 32,
              child: CircularProgressIndicator(strokeWidth: 3),
            ),
            const SizedBox(height: 16),
            Text(
              'Carregando membros...',
              style: TextStyle(
                color: isDark ? Colors.white54 : Colors.black54,
              ),
            ),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 48, color: Colors.red.shade400),
            const SizedBox(height: 16),
            Text(
              _error!,
              style: const TextStyle(color: Colors.red),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _loadCurrentMembers,
              child: const Text('Tentar Novamente'),
            ),
          ],
        ),
      );
    }

    if (_currentMembers.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: isDark ? Colors.white.withOpacity(0.05) : Colors.grey[100],
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.people_outline_rounded,
                size: 48,
                color: isDark ? Colors.white38 : Colors.black38,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Nenhum membro encontrado',
              style: TextStyle(
                color: isDark ? Colors.white54 : Colors.black54,
              ),
            ),
          ],
        ),
      );
    }

    return ListView.separated(
      itemCount: _currentMembers.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final member = _currentMembers[index];
        final session = Session();
        final isMe = member.user_id == session.myId;
        final canRemove = _myProjectRole == 'admin' && member.role != 'admin' && !isMe;

        return Container(
          decoration: BoxDecoration(
            gradient: isMe
                ? LinearGradient(
              colors: [
                t.colorScheme.primary.withOpacity(0.15),
                t.colorScheme.secondary.withOpacity(0.1),
              ],
            )
                : LinearGradient(
              colors: isDark
                  ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
                  : [Colors.white, Colors.grey[50]!],
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isMe
                  ? t.colorScheme.primary.withOpacity(0.3)
                  : (isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08)),
            ),
          ),
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            leading: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: member.role == 'admin'
                      ? [Colors.orange.shade400, Colors.orange.shade600]
                      : [Colors.blue.shade400, Colors.blue.shade600],
                ),
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: (member.role == 'admin' ? Colors.orange : Colors.blue).withOpacity(0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(
                member.role == 'admin' ? Icons.admin_panel_settings_rounded : Icons.person_rounded,
                color: Colors.white,
                size: 20,
              ),
            ),
            title: Text(
              isMe ? '${member.displayName ?? 'Você'} (você)' : member.displayName ?? 'Sem nome',
              style: TextStyle(
                fontWeight: isMe ? FontWeight.bold : FontWeight.w500,
                color: isDark ? Colors.white : Colors.black87,
              ),
            ),
            subtitle: Text(
              member.role == 'admin' ? 'Administrador' : 'Membro',
              style: TextStyle(
                fontSize: 12,
                color: isDark ? Colors.white54 : Colors.black54,
              ),
            ),
            trailing: canRemove
                ? IconButton(
              icon: const Icon(Icons.remove_circle_outline_rounded, color: Colors.red),
              onPressed: () => _showRemoveConfirmation(member),
              tooltip: 'Remover membro',
            )
                : null,
          ),
        );
      },
    );
  }

  void _showRemoveConfirmation(ProjectMember member) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        backgroundColor: isDark ? const Color(0xFF1A1F2E) : Colors.white,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.warning_rounded, color: Colors.red, size: 24),
            ),
            const SizedBox(width: 12),
            const Text('Confirmar Remoção'),
          ],
        ),
        content: Text(
          'Tem certeza que deseja remover ${member.displayName ?? 'este usuário'} do projeto?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(context);
              _removeMember(member.user_id);
            },
            style: FilledButton.styleFrom(
              backgroundColor: Colors.red,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: const Text('Remover'),
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
        if (usersData == null || usersData is! List) {
          return <AvailableUser>[];
        }
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
        body: jsonEncode({
          'new_owner_id': newOwnerId,
        }),
      );

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Projeto "$projectName" transferido com sucesso!'),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.all(16),
          ),
        );
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Erro ao transferir projeto: $e'),
          backgroundColor: Colors.red,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ),
      );
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

class ProjectMember {
  final String user_id;
  final String role;
  final String? displayName;

  ProjectMember({
    required this.user_id,
    required this.role,
    this.displayName,
  });

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    return ProjectMember(
      user_id: json['user_id'] as String,
      displayName: json['display_name'] as String?,
      role: json['role'] as String,
    );
  }
}
