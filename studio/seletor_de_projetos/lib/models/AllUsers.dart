class AllUsersResponse {
  final String projectSlug;
  final UsersSummary summary;
  final List<AvailableUser> users;

  AllUsersResponse({
    required this.projectSlug,
    required this.summary,
    required this.users,
  });

  factory AllUsersResponse.fromJson(Map<String, dynamic> json) {
    return AllUsersResponse(
      projectSlug: json['project_slug'] ?? '',
      summary: UsersSummary.fromJson(json['summary'] ?? {}),
      users: (json['users'] as List<dynamic>? ?? [])
          .map((userJson) => AvailableUser.fromJson(userJson))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'project_slug': projectSlug,
      'summary': summary.toJson(),
      'users': users.map((user) => user.toJson()).toList(),
    };
  }
}

class UsersSummary {
  final int totalUsers;
  final int currentMembers;
  final int availableUsers;
  final int orphanedMembers;
  final int cacheKeys;

  UsersSummary({
    required this.totalUsers,
    required this.currentMembers,
    required this.availableUsers,
    required this.orphanedMembers,
    required this.cacheKeys,
  });

  factory UsersSummary.fromJson(Map<String, dynamic> json) {
    return UsersSummary(
      totalUsers: json['total_users'] ?? 0,
      currentMembers: json['current_members'] ?? 0,
      availableUsers: json['available_users'] ?? 0,
      orphanedMembers: json['orphaned_members'] ?? 0,
      cacheKeys: json['cache_keys'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'total_users': totalUsers,
      'current_members': currentMembers,
      'available_users': availableUsers,
      'orphaned_members': orphanedMembers,
      'cache_keys': cacheKeys,
    };
  }
}

class AvailableUser {
  final String userId;
  final String displayName;
  final String username;
  final bool isActive;
  final String status;
  final String? projectRole;
  final String? note;

  AvailableUser({
    required this.userId,
    required this.displayName,
    required this.username,
    required this.isActive,
    required this.status,
    this.projectRole,
    this.note,
  });

  factory AvailableUser.fromJson(Map<String, dynamic> json) {
    return AvailableUser(
      userId: json['user_id'] ?? '',
      displayName: json['display_name'] ?? 'Unknown',
      username: json['username'] ?? 'unknown',
      isActive: json['is_active'] ?? false,
      status: json['status'] ?? 'available',
      projectRole: json['project_role'],
      note: json['note'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'user_id': userId,
      'display_name': displayName,
      'username': username,
      'is_active': isActive,
      'status': status,
      if (projectRole != null) 'project_role': projectRole,
      if (note != null) 'note': note,
    };
  }

  bool get isMember => status == 'member';
  bool get isAvailable => status == 'available';
}

class AvailableUserShort {
  final String userId;
  final String displayName;

  AvailableUserShort({required this.userId, required this.displayName});

  factory AvailableUserShort.fromJson(Map<String, dynamic> j) =>
      AvailableUserShort(
        userId:       j['user_id'] as String,
        displayName:  j['display_name'] as String,
      );
}
