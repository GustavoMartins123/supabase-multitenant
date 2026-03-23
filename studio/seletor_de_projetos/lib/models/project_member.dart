class ProjectMember {
  final String user_id;
  final String role;
  final String? displayName;

  ProjectMember({
    required this.user_id,
    required this.role,
    this.displayName,
  });

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    return ProjectMember(
      user_id: json['user_id'] as String,
      displayName: json['display_name'] as String?,
      role: json['role'] as String,
    );
  }
}
