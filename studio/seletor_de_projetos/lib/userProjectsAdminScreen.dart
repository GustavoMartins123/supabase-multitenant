import 'dart:convert';
import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/projectSettingsDialog.dart';
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';
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

class _UserProjectsAdminScreenState extends State<UserProjectsAdminScreen> with SingleTickerProviderStateMixin {
  List<ProjectInfo> _projects = [];
  bool _loading = true;
  final Session _session = Session();
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _session.busyListenable.addListener(_onBusyChanged);
    _fetchProjects();
    
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 500),
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
    if (mounted) {
      setState(fn);
    }
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
        await _fetchProjects();
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
      if (kDebugMode) {
        print(e);
      }
    } finally {
      _safeSetState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? const Color(0xFF0A0E1A) : const Color(0xFFF5F7FA),
      body: CustomScrollView(
        slivers: [
          SliverAppBar.large(
            floating: true,
            pinned: true,
            backgroundColor: isDark ? const Color(0xFF0F1419) : Colors.white,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_rounded),
              onPressed: () => Navigator.of(context).pop(),
            ),
            flexibleSpace: FlexibleSpaceBar(
              titlePadding: const EdgeInsets.only(left: 60, bottom: 16),
              title: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Projetos',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.white : Colors.black87,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              t.colorScheme.primary.withOpacity(0.2),
                              t.colorScheme.secondary.withOpacity(0.2),
                            ],
                          ),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          widget.userName,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: t.colorScheme.primary,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '• ${_projects.length} ${_projects.length == 1 ? 'projeto' : 'projetos'}',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.normal,
                          color: isDark ? Colors.white54 : Colors.black45,
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
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    if (_loading) {
      return Padding(
        padding: const EdgeInsets.all(80),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 50,
                height: 50,
                child: CircularProgressIndicator(
                  strokeWidth: 3,
                  color: t.colorScheme.primary,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'Carregando projetos...',
                style: TextStyle(
                  color: isDark ? Colors.white70 : Colors.black54,
                  fontSize: 15,
                ),
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
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      t.colorScheme.primary.withOpacity(0.2),
                      t.colorScheme.secondary.withOpacity(0.1),
                    ],
                  ),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.folder_open_rounded,
                  size: 56,
                  color: t.colorScheme.primary,
                ),
              ),
              const SizedBox(height: 32),
              Text(
                'Nenhum projeto encontrado',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.white : Colors.black87,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Este usuário ainda não possui projetos',
                style: TextStyle(
                  fontSize: 15,
                  color: isDark ? Colors.white60 : Colors.black54,
                ),
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
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Column(
            children: _projects.map(_buildProjectCard).toList(),
          ),
        ),
      ),
    );
  }

  Widget _buildProjectCard(ProjectInfo project) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;
    final busy = _session.isBusy(project.name);

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
          margin: const EdgeInsets.only(bottom: 16),
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
            boxShadow: [
              BoxShadow(
                color: isDark ? Colors.black.withOpacity(0.3) : Colors.black.withOpacity(0.08),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
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
                            project.name,
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              color: isDark ? Colors.white : Colors.black87,
                              letterSpacing: -0.3,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: isRunning
                                      ? Colors.green.withOpacity(0.15)
                                      : Colors.orange.withOpacity(0.15),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  effectiveStatus.toUpperCase(),
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                    color: isRunning ? Colors.green : Colors.orange,
                                    letterSpacing: 0.5,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Icon(
                                Icons.widgets_rounded,
                                size: 14,
                                color: isDark ? Colors.white38 : Colors.black38,
                              ),
                              const SizedBox(width: 6),
                              Text(
                                '$running/$total containers',
                                style: TextStyle(
                                  fontSize: 13,
                                  color: isDark ? Colors.white60 : Colors.black54,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    if (busy)
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: t.colorScheme.primary.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(t.colorScheme.primary),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Divider(color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08)),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildActionButton(
                        icon: Icons.open_in_new_rounded,
                        label: 'Abrir',
                        color: t.colorScheme.primary,
                        onPressed: busy ? null : () => _openProject(project.name),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _buildActionButton(
                        icon: Icons.play_arrow_rounded,
                        label: 'Start',
                        color: Colors.green,
                        onPressed: busy ? null : () => _doAction(project.name, 'start'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _buildActionButton(
                        icon: Icons.stop_rounded,
                        label: 'Stop',
                        color: Colors.red,
                        onPressed: busy ? null : () => _doAction(project.name, 'stop'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _buildActionButton(
                        icon: Icons.restart_alt_rounded,
                        label: 'Restart',
                        color: Colors.blue,
                        onPressed: busy ? null : () => _doAction(project.name, 'restart'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _buildActionButton(
                        icon: Icons.swap_horiz_rounded,
                        label: 'Transferir',
                        color: Colors.purple,
                        onPressed: busy ? null : () => _showTransferDialog(project.name),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _buildActionButton(
                        icon: Icons.delete_outline_rounded,
                        label: 'Excluir',
                        color: Colors.red.shade700,
                        onPressed: busy ? null : () => _confirmAndDelete(project.name),
                      ),
                    ),
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
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
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
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                color: onPressed == null ? Colors.grey : color,
                size: 20,
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: onPressed == null ? Colors.grey : color,
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
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Ação "$action" executada no projeto "$projectName".'),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.all(16),
          ),
        );
        await _fetchProjects();
      } else {
        throw Exception('Erro: ${resp.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.toString()),
          backgroundColor: Colors.red,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ),
      );
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
