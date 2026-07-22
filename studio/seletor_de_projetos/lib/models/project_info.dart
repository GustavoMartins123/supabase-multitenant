import 'package:seletor_de_projetos/models/project_docker_status.dart';

class ProjectInfo {
  final String name;
  final String status;
  final int runningContainers;
  final int totalContainers;
  final String fileSizeLimit;
  final String storageLimitToken;
  Future<ProjectDockerStatus>? statusFuture;
  ProjectInfo({
    required this.name,
    required this.status,
    required this.runningContainers,
    required this.totalContainers,
    required this.fileSizeLimit,
    required this.storageLimitToken,
  });

  factory ProjectInfo.fromJson(Map<String, dynamic> json) => ProjectInfo(
        name: json['name'],
        status: json['status'],
        runningContainers: json['running_containers'],
        totalContainers: json['total_containers'],
        fileSizeLimit: json['file_size_limit']?.toString() ?? '',
        storageLimitToken: json['storage_limit_token']?.toString() ?? '',
      );
}
