class UserListResponse {
  final List<UserInfo> users;
  final UserSummary summary;
  final int timestamp;

  UserListResponse({
    required this.users,
    required this.summary,
    required this.timestamp,
  });

  factory UserListResponse.fromJson(Map<String, dynamic> json) {
    List<UserInfo> usersList = [];
    if (json['users'] != null) {
      if (json['users'] is List) {
        usersList = (json['users'] as List)
            .map((u) => UserInfo.fromJson(u))
            .toList();
      }
    }

    return UserListResponse(
      users: usersList,
      summary: UserSummary.fromJson(json['summary'] ?? {}),
      timestamp: json['timestamp'] ?? 0,
    );
  }
}

class UserInfo {
  final String id;
  final String username;
  final String displayName;
  final bool isActive;
  final String status;
  final String emailHint;

  UserInfo({
    required this.id,
    required this.username,
    required this.displayName,
    required this.isActive,
    required this.status,
    required this.emailHint,
  });

  factory UserInfo.fromJson(Map<String, dynamic> json) {
    return UserInfo(
      id: json['id'] ?? '',
      username: json['username'] ?? '',
      displayName: json['display_name'] ?? '',
      isActive: json['is_active'] ?? false,
      status: json['status'] ?? 'unknown',
      emailHint: json['email_hint'] ?? '',
    );
  }
}

class UserSummary {
  final int total;
  final int active;
  final int inactive;

  UserSummary({
    required this.total,
    required this.active,
    required this.inactive,
  });

  factory UserSummary.fromJson(Map<String, dynamic> json) {
    return UserSummary(
      total: json['total'] ?? 0,
      active: json['active'] ?? 0,
      inactive: json['inactive'] ?? 0,
    );
  }
}
