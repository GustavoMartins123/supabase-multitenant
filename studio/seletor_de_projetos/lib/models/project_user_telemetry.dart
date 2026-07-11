class ProjectTelemetryUser {
  const ProjectTelemetryUser({
    required this.userId,
    required this.sessionCount,
    this.email,
    this.phone,
    this.lastLoginAt,
  });

  final String userId;
  final String? email;
  final String? phone;
  final DateTime? lastLoginAt;
  final int sessionCount;

  String get displayName {
    if (email != null && email!.isNotEmpty) return email!;
    if (phone != null && phone!.isNotEmpty) return phone!;
    return userId;
  }

  factory ProjectTelemetryUser.fromJson(Map<String, dynamic> json) {
    final lastLogin = json['last_login_at']?.toString();
    return ProjectTelemetryUser(
      userId: json['user_id']?.toString() ?? '',
      email: json['email']?.toString(),
      phone: json['phone']?.toString(),
      lastLoginAt: lastLogin == null ? null : DateTime.tryParse(lastLogin),
      sessionCount: (json['session_count'] as num?)?.toInt() ?? 0,
    );
  }
}

class ProjectUserTelemetry {
  const ProjectUserTelemetry({
    required this.project,
    required this.period,
    required this.start,
    required this.end,
    required this.activeUsers,
    required this.totalSessions,
    required this.users,
    required this.sessionsAreCurrentRecords,
  });

  final String project;
  final String period;
  final DateTime start;
  final DateTime end;
  final int activeUsers;
  final int totalSessions;
  final List<ProjectTelemetryUser> users;
  final bool sessionsAreCurrentRecords;

  factory ProjectUserTelemetry.fromJson(Map<String, dynamic> json) {
    final rawUsers = json['users'] as List<dynamic>? ?? const [];
    return ProjectUserTelemetry(
      project: json['project']?.toString() ?? '',
      period: json['period']?.toString() ?? '',
      start: DateTime.parse(json['start'].toString()),
      end: DateTime.parse(json['end'].toString()),
      activeUsers: (json['active_users'] as num?)?.toInt() ?? 0,
      totalSessions: (json['total_sessions'] as num?)?.toInt() ?? 0,
      users: rawUsers
          .map(
            (item) => ProjectTelemetryUser.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
      sessionsAreCurrentRecords: json['sessions_are_current_records'] == true,
    );
  }
}
