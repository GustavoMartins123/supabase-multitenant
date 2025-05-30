// Models for UserProjectsAdminScreen
class AdminProjectInfo {
  final String id; // Project's database ID
  final String name;
  final String dockerStatus;
  final int containersRunning;
  final int containersTotal;
  final bool isCallerProjectAdmin;

  AdminProjectInfo({
    required this.id,
    required this.name,
    required this.dockerStatus,
    required this.containersRunning,
    required this.containersTotal,
    required this.isCallerProjectAdmin,
  });

  factory AdminProjectInfo.fromJson(Map<String, dynamic> json) {
    return AdminProjectInfo(
      id: json['id'] as String,
      name: json['name'] as String,
      dockerStatus: json['docker_status'] as String,
      containersRunning: json['containers_running'] as int,
      containersTotal: json['containers_total'] as int,
      isCallerProjectAdmin: json['is_caller_project_admin'] as bool,
    );
  }
}