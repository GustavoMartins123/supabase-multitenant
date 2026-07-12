class ProjectMember {
  final String user_id;
  final String? userHash;
  final String role;
  final String? displayName;
  final String? pictureUrl;

  ProjectMember({
    required this.user_id,
    required this.role,
    this.displayName,
    this.userHash,
    this.pictureUrl,
  });

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    return ProjectMember(
      user_id: (json['user_id'] ?? json['user_uuid'] ?? '') as String,
      userHash: json['user_hash'] as String?,
      displayName: json['display_name'] as String?,
      role: json['role'] as String,
      pictureUrl: json['picture_url'] as String?,
    );
  }
}
