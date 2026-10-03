// Project projection used by the administrative user screen.
class AdminProjectInfo {
  final String id; // Project's database ID
  final String name;
  final String publicRef;
  final String dockerStatus;
  final int containersRunning;
  final int containersTotal;
  final bool isCallerProjectAdmin;

  AdminProjectInfo({
    required this.id,
    required this.name,
    required this.publicRef,
    required this.dockerStatus,
    required this.containersRunning,
    required this.containersTotal,
    required this.isCallerProjectAdmin,
  });

  factory AdminProjectInfo.fromJson(Map<String, dynamic> json) {
    return AdminProjectInfo(
      id: json['id'] as String,
      name: json['name'] as String,
      publicRef: json['public_ref'] as String,
      dockerStatus: json['status'] as String,
      containersRunning: json['running_containers'] as int,
      containersTotal: json['total_containers'] as int,
      isCallerProjectAdmin: json['is_caller_project_admin'] as bool,
    );
  }
}
