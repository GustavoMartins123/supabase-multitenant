import 'project_identity.dart';

import 'package:seletor_de_projetos/models/project_docker_status.dart';

class ProjectInfo {
  final ProjectIdentity identity;
  String get projectUuid => identity.projectUuid;
  String get name => identity.name;
  String get displayName => identity.displayName;
  String get publicRef => identity.publicRef;
  final String status;
  final int runningContainers;
  final int totalContainers;
  final String fileSizeLimit;
  final String storageLimitToken;
  Future<ProjectDockerStatus>? statusFuture;
  ProjectInfo({
    required this.identity,
    required this.status,
    required this.runningContainers,
    required this.totalContainers,
    required this.fileSizeLimit,
    required this.storageLimitToken,
  });

  factory ProjectInfo.fromJson(Map<String, dynamic> json) => ProjectInfo(
        identity: ProjectIdentity.fromJson(json),
        status: json['status'],
        runningContainers: json['running_containers'],
        totalContainers: json['total_containers'],
        fileSizeLimit: json['file_size_limit']?.toString() ?? '',
        storageLimitToken: json['storage_limit_token']?.toString() ?? '',
      );
}
