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

class _UserProjectsAdminScreenState extends State<UserProjectsAdminScreen> {
  List<ProjectInfo> _projects = [];
  bool _loading = true;
  final Session _session = Session();

  @override
  void initState() {
    super.initState();
    _session.busyListenable.addListener(_onBusyChanged);
    _fetchProjects();
  }

  @override
  void dispose() {
    _session.busyListenable.removeListener(_onBusyChanged);
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
          SnackBar(content: Text('Projeto "$projectName" transferido com sucesso!')),
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
    return Scaffold(
      appBar: AppBar(
        title: Text('Projetos de ${widget.userName}'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _projects.isEmpty
          ? const Center(child: Text('Nenhum projeto encontrado'))
          : ListView(
        padding: const EdgeInsets.all(16),
        children: _projects.map(_buildProjectCard).toList(),
      ),
    );
  }

  Widget _buildProjectCard(ProjectInfo project) {
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
        final running        = snap.data?.running  ?? project.runningContainers;
        final total          = snap.data?.total    ?? project.totalContainers;

        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Icon(
                  effectiveStatus == 'running'
                      ? Icons.check_circle
                      : Icons.warning,
                  color: effectiveStatus == 'running'
                      ? Colors.green
                      : Colors.orange,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(project.name,
                          style: const TextStyle(fontWeight: FontWeight.bold)),
                      const SizedBox(height: 4),
                      Text(
                        'Containers: $running/$total',
                        style:
                        TextStyle(color: Colors.grey[700], fontSize: 12),
                      ),
                    ],
                  ),
                ),
                Row(
                  children: [
                    IconButton(
                      tooltip: 'Abrir',
                      icon: const Icon(Icons.open_in_new),
                      onPressed: () => _openProject(project.name),
                    ),
                    IconButton(
                      tooltip: 'Start',
                      icon: const Icon(Icons.play_arrow),
                      onPressed: busy
                          ? null
                          : () => _doAction(project.name, 'start'),
                    ),
                    IconButton(
                      tooltip: 'Stop',
                      icon: const Icon(Icons.stop),
                      onPressed: busy
                          ? null
                          : () => _doAction(project.name, 'stop'),
                    ),
                    IconButton(
                      tooltip: 'Restart',
                      icon: const Icon(Icons.restart_alt),
                      onPressed: busy
                          ? null
                          : () => _doAction(project.name, 'restart'),
                    ),
                    IconButton(
                      tooltip: 'Transferir projeto',
                      icon: const Icon(Icons.transfer_within_a_station, color: Colors.blue),
                      onPressed: busy
                          ? null
                          : () => _showTransferDialog(project.name),
                    ),
                    IconButton(
                      tooltip: 'Excluir',
                      icon: const Icon(Icons.delete, color: Colors.red),
                      onPressed: busy
                          ? null
                          : () => _confirmAndDelete(project.name),
                    ),
                    if (busy)
                      const Padding(
                        padding: EdgeInsets.only(left: 8),
                        child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
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
          SnackBar(content: Text('Ação "$action" executada no projeto "$projectName".')),
        );
        await _fetchProjects();
      } else {
        throw Exception('Erro: ${resp.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), backgroundColor: Colors.red),
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