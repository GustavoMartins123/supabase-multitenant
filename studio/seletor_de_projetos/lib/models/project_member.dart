class ProjectMember {
  final String user_id;
  final String? userHash;
  final String role;
  final String? displayName;

  ProjectMember({
    required this.user_id,
    required this.role,
    this.displayName,
    this.userHash,
  });

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    return ProjectMember(
      user_id: (json['user_id'] ?? json['user_uuid'] ?? '') as String,
      userHash: json['user_hash'] as String?,
      displayName: json['display_name'] as String?,
      role: json['role'] as String,
    );
  }
}
