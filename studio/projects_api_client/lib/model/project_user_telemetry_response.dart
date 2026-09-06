//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectUserTelemetryResponse {
  /// Returns a new [ProjectUserTelemetryResponse] instance.
  ProjectUserTelemetryResponse({
    required this.activeUsers,
    required this.end,
    required this.period,
    required this.project,
    required this.sessionsAreCurrentRecords,
    required this.source_,
    required this.start,
    required this.totalSessions,
    this.users = const [],
  });

  int activeUsers;

  String end;

  String period;

  String project;

  bool sessionsAreCurrentRecords;

  String source_;

  String start;

  int totalSessions;

  List<TelemetryUserItem> users;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectUserTelemetryResponse &&
    other.activeUsers == activeUsers &&
    other.end == end &&
    other.period == period &&
    other.project == project &&
    other.sessionsAreCurrentRecords == sessionsAreCurrentRecords &&
    other.source_ == source_ &&
    other.start == start &&
    other.totalSessions == totalSessions &&
    _deepEquality.equals(other.users, users);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (activeUsers.hashCode) +
    (end.hashCode) +
    (period.hashCode) +
    (project.hashCode) +
    (sessionsAreCurrentRecords.hashCode) +
    (source_.hashCode) +
    (start.hashCode) +
    (totalSessions.hashCode) +
    (users.hashCode);

  @override
  String toString() => 'ProjectUserTelemetryResponse[activeUsers=$activeUsers, end=$end, period=$period, project=$project, sessionsAreCurrentRecords=$sessionsAreCurrentRecords, source_=$source_, start=$start, totalSessions=$totalSessions, users=$users]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'active_users'] = this.activeUsers;
      json[r'end'] = this.end;
      json[r'period'] = this.period;
      json[r'project'] = this.project;
      json[r'sessions_are_current_records'] = this.sessionsAreCurrentRecords;
      json[r'source'] = this.source_;
      json[r'start'] = this.start;
      json[r'total_sessions'] = this.totalSessions;
      json[r'users'] = this.users;
    return json;
  }

  /// Returns a new [ProjectUserTelemetryResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectUserTelemetryResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectUserTelemetryResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectUserTelemetryResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectUserTelemetryResponse(
        activeUsers: mapValueOfType<int>(json, r'active_users')!,
        end: mapValueOfType<String>(json, r'end')!,
        period: mapValueOfType<String>(json, r'period')!,
        project: mapValueOfType<String>(json, r'project')!,
        sessionsAreCurrentRecords: mapValueOfType<bool>(json, r'sessions_are_current_records')!,
        source_: mapValueOfType<String>(json, r'source')!,
        start: mapValueOfType<String>(json, r'start')!,
        totalSessions: mapValueOfType<int>(json, r'total_sessions')!,
        users: TelemetryUserItem.listFromJson(json[r'users']),
      );
    }
    return null;
  }

  static List<ProjectUserTelemetryResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectUserTelemetryResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectUserTelemetryResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectUserTelemetryResponse> mapFromJson(dynamic json) {
    final map = <String, ProjectUserTelemetryResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectUserTelemetryResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectUserTelemetryResponse-objects as value to a dart map
  static Map<String, List<ProjectUserTelemetryResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectUserTelemetryResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectUserTelemetryResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'active_users',
    'end',
    'period',
    'project',
    'sessions_are_current_records',
    'source',
    'start',
    'total_sessions',
    'users',
  };
}

