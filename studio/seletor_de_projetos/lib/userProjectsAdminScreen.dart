import 'dart:convert';
import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';
import 'dart:html' as html;
import 'dialogs/transferProjectDialog.dart';
import 'models/AllUsers.dart';
import 'models/ProjectInfo.dart';
import 'models/projectDockerStatus.dart';

class UserProjectsAdminScreen extends StatefulWidget {
  final String userIdHash;
  final String userName;

  const UserProjectsAdminScreen({
    super.key,
    required this.userIdHash,
    required this.userName,
  });

  @override
  State<UserProjectsAdminScreen> createState() => _UserProjectsAdminScreenState();
}

class _UserProjectsAdminScreenState extends State<UserProjectsAdminScreen>
    with SingleTickerProviderStateMixin {
  List<ProjectInfo> _projects = [];
  bool _loading = true;
  String? _serverDomain;
  final Session _session = Session();
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _session.busyListenable.addListener(_onBusyChanged);
    _fetchProjects();
    _fetchConfig();

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    );
    _fadeController.forward();
  }

  @override
  void dispose() {
    _session.busyListenable.removeListener(_onBusyChanged);
    _fadeController.dispose();
    super.dispose();
  }

  void _onBusyChanged() {
    if (!mounted) return;

    if (!_projects.any((p) => _session.isBusy(p.name))) {
      _fetchProjects();
    }
    _safeSetState(() {});
  }

  void _safeSetState(VoidCallback fn) {
    if (mounted) setState(fn);
  }

  Future<void> _fetchConfig() async {
    try {
      final r = await http.get(Uri.parse('/api/config'));
      if (r.statusCode == 200) {
        final data = jsonDecode(r.body);
        _safeSetState(() => _serverDomain = data['server_domain']);
      }
    } catch (_) {}
  }

  Future<List<AvailableUser>> _loadAvailableUsers(String projectName) async {
    try {
      final response = await http.get(
        Uri.parse('/api/admin/projects/$projectName/all-users'),
      );

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        final List<dynamic> usersJson = data['users'];

        return usersJson
            .map((item) => AvailableUser.fromJson(item))
            .where((user) => user.isActive == true)
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
        _showSnack('Projeto "$projectName" transferido!', SupabaseColors.success);
        await _fetchProjects();
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

  Future<void> _fetchProjects() async {
    _safeSetState(() => _loading = true);
    try {
      final response = await http.post(
        Uri.parse('/api/admin/projects-info'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({"user_id": widget.userIdHash}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final projectsJson = data["projects"] as List;
        _projects = projectsJson.map((p) => ProjectInfo.fromJson(p)).toList();
      } else {
        throw Exception('Erro ao carregar projetos: ${response.body}');
      }
    } catch (e) {
      if (kDebugMode) print(e);
    } finally {
      _safeSetState(() => _loading = false);
    }
  }

  void _showSnack(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: const TextStyle(color: Colors.white)),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }

  String _getProjectUrl(String projectName) {
    if (_serverDomain == null || _serverDomain!.isEmpty) return projectName;
    return '$_serverDomain/$projectName';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            floating: true,
            pinned: true,
            expandedHeight: 100,
            backgroundColor: SupabaseColors.bg100,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_rounded, color: SupabaseColors.textSecondary),
              onPressed: () => Navigator.of(context).pop(),
            ),
            flexibleSpace: FlexibleSpaceBar(
              titlePadding: const EdgeInsets.only(left: 56, bottom: 16),
              title: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Projetos',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                      color: SupabaseColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: SupabaseColors.brand.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          widget.userName,
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: SupabaseColors.brand,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '• ${_projects.length} ${_projects.length == 1 ? 'projeto' : 'projetos'}',
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.normal,
                          color: SupabaseColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: _buildContent(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(80),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 32,
                height: 32,
                child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
              ),
              SizedBox(height: 16),
              Text(
                'Carregando projetos...',
                style: TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
              ),
            ],
          ),
        ),
      );
    }

    if (_projects.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(80),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  color: SupabaseColors.surface200,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Icon(
                  Icons.folder_open_rounded,
                  size: 36,
                  color: SupabaseColors.textMuted,
                ),
              ),
              const SizedBox(height: 20),
              const Text(
                'Nenhum projeto encontrado',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: SupabaseColors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Este usuário ainda não possui projetos',
                style: TextStyle(fontSize: 13, color: SupabaseColors.textMuted),
              ),
            ],
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1000),
          child: Column(
            children: _projects.map((p) => _buildProjectCard(p)).toList(),
          ),
        ),
      ),
    );
  }

  Widget _buildProjectCard(ProjectInfo project) {
    final busy = _session.isBusy(project.name);
    final projectUrl = _getProjectUrl(project.name);

    if (project.statusFuture == null && !busy) {
      project.statusFuture = http
          .get(Uri.parse('/api/projects/${project.name}/status'))
          .then((r) => ProjectDockerStatus.fromJson(jsonDecode(r.body)));
    }

    return FutureBuilder<ProjectDockerStatus>(
      future: project.statusFuture,
      builder: (context, snap) {
        final effectiveStatus = snap.data?.status ?? project.status;
        final running = snap.data?.running ?? project.runningContainers;
        final total = snap.data?.total ?? project.totalContainers;
        final isRunning = effectiveStatus == 'running';

        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(
            color: SupabaseColors.surface100,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: isRunning
                  ? SupabaseColors.success.withOpacity(0.3)
                  : SupabaseColors.warning.withOpacity(0.3),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  children: [
                    Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isRunning ? SupabaseColors.success : SupabaseColors.warning,
                        boxShadow: [
                          BoxShadow(
                            color: (isRunning ? SupabaseColors.success : SupabaseColors.warning)
                                .withOpacity(0.5),
                            blurRadius: 6,
                            spreadRadius: 1,
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
                            project.name,
                            style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              color: SupabaseColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  projectUrl,
                                  style: const TextStyle(
                                    fontSize: 11,
                                    fontFamily: 'monospace',
                                    color: SupabaseColors.textMuted,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              const SizedBox(width: 4),
                              _MiniIconBtn(
                                icon: Icons.link_rounded,
                                tooltip: 'Copiar URL',
                                onPressed: () {
                                  Clipboard.setData(ClipboardData(text: projectUrl));
                                  _showSnack('URL copiada!', SupabaseColors.success);
                                },
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: isRunning
                                      ? SupabaseColors.success.withOpacity(0.15)
                                      : SupabaseColors.warning.withOpacity(0.15),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  effectiveStatus.toUpperCase(),
                                  style: TextStyle(
                                    fontSize: 9,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0.5,
                                    color: isRunning ? SupabaseColors.success : SupabaseColors.warning,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                '$running/$total containers',
                                style: const TextStyle(fontSize: 11, color: SupabaseColors.textMuted),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),

                    if (busy)
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: SupabaseColors.brand.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
                        ),
                      ),
                  ],
                ),

                const SizedBox(height: 12),
                const Divider(color: SupabaseColors.border, height: 1),
                const SizedBox(height: 12),

                Row(
                  children: [
                    Expanded(child: _buildActionButton(
                      icon: Icons.open_in_new_rounded,
                      label: 'Abrir',
                      color: SupabaseColors.brand,
                      onPressed: busy ? null : () => _openProject(project.name),
                    )),
                    const SizedBox(width: 6),
                    Expanded(child: _buildActionButton(
                      icon: Icons.play_arrow_rounded,
                      label: 'Start',
                      color: SupabaseColors.success,
                      onPressed: busy ? null : () => _doAction(project.name, 'start'),
                    )),
                    const SizedBox(width: 6),
                    Expanded(child: _buildActionButton(
                      icon: Icons.stop_rounded,
                      label: 'Stop',
                      color: SupabaseColors.error,
                      onPressed: busy ? null : () => _doAction(project.name, 'stop'),
                    )),
                    const SizedBox(width: 6),
                    Expanded(child: _buildActionButton(
                      icon: Icons.restart_alt_rounded,
                      label: 'Restart',
                      color: SupabaseColors.info,
                      onPressed: busy ? null : () => _doAction(project.name, 'restart'),
                    )),
                    const SizedBox(width: 6),
                    Expanded(child: _buildActionButton(
                      icon: Icons.swap_horiz_rounded,
                      label: 'Transferir',
                      color: Colors.purple,
                      onPressed: busy ? null : () => _showTransferDialog(project.name),
                    )),
                    const SizedBox(width: 6),
                    Expanded(child: _buildActionButton(
                      icon: Icons.delete_outline_rounded,
                      label: 'Excluir',
                      color: SupabaseColors.error,
                      onPressed: busy ? null : () => _confirmAndDelete(project.name),
                    )),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback? onPressed,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: onPressed == null ? SupabaseColors.bg300 : color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: onPressed == null ? SupabaseColors.border : color.withOpacity(0.3),
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                color: onPressed == null ? SupabaseColors.textMuted : color,
                size: 16,
              ),
              const SizedBox(height: 2),
              Text(
                label,
                style: TextStyle(
                  fontSize: 9,
                  fontWeight: FontWeight.w500,
                  color: onPressed == null ? SupabaseColors.textMuted : color,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openProject(String ref) async {
    await http.get(Uri.parse('/set-project?ref=$ref'));
    html.window.open('${html.window.location.origin}/project/default', '_blank');
  }

  void _doAction(String projectName, String action) async {
    _session.setBusy(projectName, true);
    try {
      final resp = await http.post(
        Uri.parse('/api/projects/$projectName/$action'),
      );

      if (resp.statusCode == 200) {
        _showSnack('Ação "$action" executada em "$projectName"', SupabaseColors.success);
        await _fetchProjects();
      } else {
        throw Exception('Erro: ${resp.body}');
      }
    } catch (e) {
      _showSnack(e.toString(), SupabaseColors.error);
    } finally {
      final proj = _projects.firstWhereOrNull((p) => p.name == projectName);
      if (proj != null) proj.statusFuture = null;
      _session.setBusy(projectName, false);
    }
  }

  void _confirmAndDelete(String projectName) async {
    bool sucesso = await ProjectService.confirmAndDeleteProject(context, projectName);

    if (sucesso) {
      _safeSetState(() {
        _projects.removeWhere((project) => project.name == projectName);
      });
    }
  }
}

class _MiniIconBtn extends StatelessWidget {
  const _MiniIconBtn({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

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
            padding: const EdgeInsets.all(4),
            child: Icon(icon, size: 14, color: SupabaseColors.textMuted),
          ),
        ),
      ),
    );
  }
}