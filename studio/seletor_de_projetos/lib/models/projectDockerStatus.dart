class ProjectDockerStatus {
  final String status;            // running | stopped | partial | unknown
  final int running;
  final int total;

  ProjectDockerStatus({
    required this.status,
    required this.running,
    required this.total,
  });

  factory ProjectDockerStatus.fromJson(Map<String, dynamic> json) {
    return ProjectDockerStatus(
      status: json['status'] as String? ?? 'unknown',
      running: json['running'] as int? ?? 0,
      total:   json['total'] as int? ?? 0,
    );
  }
}
