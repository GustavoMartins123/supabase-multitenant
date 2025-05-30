import 'dart:convert';
import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';

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

class ProjectInfo {
  final String name;
  final String status;
  final int runningContainers;
  final int totalContainers;
  Future<ProjectDockerStatus>? statusFuture;
  ProjectInfo({
    required this.name,
    required this.status,
    required this.runningContainers,
    required this.totalContainers,
  });

  factory ProjectInfo.fromJson(Map<String, dynamic> json) => ProjectInfo(
    name: json['name'],
    status: json['status'],
    runningContainers: json['running_containers'],
    totalContainers: json['total_containers'],
  );
}
