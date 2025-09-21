import 'package:seletor_de_projetos/models/projectDockerStatus.dart';

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