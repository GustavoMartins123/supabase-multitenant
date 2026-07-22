class ProjectMember {
  final String userId;
  final String? userHash;
  final String role;
  final String? displayName;
  final String? pictureUrl;

  ProjectMember({
    required this.userId,
    required this.role,
    this.displayName,
    this.userHash,
    this.pictureUrl,
  });

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    final userId = (json['user_id'] ?? json['user_uuid'])?.toString() ?? '';
    final role = json['role']?.toString() ?? '';
    if (userId.isEmpty || role.isEmpty) {
      throw const FormatException('Membro sem identificador ou papel');
    }
    return ProjectMember(
      userId: userId,
      userHash: json['user_hash']?.toString(),
      displayName: json['display_name']?.toString(),
      role: role,
      pictureUrl: json['picture_url']?.toString(),
    );
  }
}
