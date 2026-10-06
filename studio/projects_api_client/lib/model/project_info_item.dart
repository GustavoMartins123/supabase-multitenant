//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectInfoItem {
  /// Returns a new [ProjectInfoItem] instance.
  ProjectInfoItem({
    required this.displayName,
    required this.fileSizeLimit,
    required this.isCallerProjectAdmin,
    required this.name,
    required this.projectUuid,
    required this.publicRef,
    required this.runningContainers,
    required this.status,
    required this.storageLimitToken,
    required this.tenantUuid,
    required this.totalContainers,
  });

  String displayName;

  String fileSizeLimit;

  bool isCallerProjectAdmin;

  String name;

  String projectUuid;

  String publicRef;

  int runningContainers;

  String status;

  String storageLimitToken;

  String? tenantUuid;

  int totalContainers;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectInfoItem &&
    other.displayName == displayName &&
    other.fileSizeLimit == fileSizeLimit &&
    other.isCallerProjectAdmin == isCallerProjectAdmin &&
    other.name == name &&
    other.projectUuid == projectUuid &&
    other.publicRef == publicRef &&
    other.runningContainers == runningContainers &&
    other.status == status &&
    other.storageLimitToken == storageLimitToken &&
    other.tenantUuid == tenantUuid &&
    other.totalContainers == totalContainers;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName.hashCode) +
    (fileSizeLimit.hashCode) +
    (isCallerProjectAdmin.hashCode) +
    (name.hashCode) +
    (projectUuid.hashCode) +
    (publicRef.hashCode) +
    (runningContainers.hashCode) +
    (status.hashCode) +
    (storageLimitToken.hashCode) +
    (tenantUuid == null ? 0 : tenantUuid!.hashCode) +
    (totalContainers.hashCode);

  @override
  String toString() => 'ProjectInfoItem[displayName=$displayName, fileSizeLimit=$fileSizeLimit, isCallerProjectAdmin=$isCallerProjectAdmin, name=$name, projectUuid=$projectUuid, publicRef=$publicRef, runningContainers=$runningContainers, status=$status, storageLimitToken=$storageLimitToken, tenantUuid=$tenantUuid, totalContainers=$totalContainers]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'display_name'] = this.displayName;
      json[r'file_size_limit'] = this.fileSizeLimit;
      json[r'is_caller_project_admin'] = this.isCallerProjectAdmin;
      json[r'name'] = this.name;
      json[r'project_uuid'] = this.projectUuid;
      json[r'public_ref'] = this.publicRef;
      json[r'running_containers'] = this.runningContainers;
      json[r'status'] = this.status;
      json[r'storage_limit_token'] = this.storageLimitToken;
    if (this.tenantUuid != null) {
      json[r'tenant_uuid'] = this.tenantUuid;
    } else {
      json[r'tenant_uuid'] = null;
    }
      json[r'total_containers'] = this.totalContainers;
    return json;
  }

  /// Returns a new [ProjectInfoItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectInfoItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'tenant_uuid'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return ProjectInfoItem(
        displayName: mapValueOfType<String>(json, r'display_name')!,
        fileSizeLimit: mapValueOfType<String>(json, r'file_size_limit')!,
        isCallerProjectAdmin: mapValueOfType<bool>(json, r'is_caller_project_admin')!,
        name: mapValueOfType<String>(json, r'name')!,
        projectUuid: mapValueOfType<String>(json, r'project_uuid')!,
        publicRef: mapValueOfType<String>(json, r'public_ref')!,
        runningContainers: mapValueOfType<int>(json, r'running_containers')!,
        status: mapValueOfType<String>(json, r'status')!,
        storageLimitToken: mapValueOfType<String>(json, r'storage_limit_token')!,
        tenantUuid: mapValueOfType<String>(json, r'tenant_uuid'),
        totalContainers: mapValueOfType<int>(json, r'total_containers')!,
      );
    }
    return null;
  }

  static List<ProjectInfoItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectInfoItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectInfoItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectInfoItem> mapFromJson(dynamic json) {
    final map = <String, ProjectInfoItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectInfoItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectInfoItem-objects as value to a dart map
  static Map<String, List<ProjectInfoItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectInfoItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectInfoItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'display_name',
    'file_size_limit',
    'is_caller_project_admin',
    'name',
    'project_uuid',
    'public_ref',
    'running_containers',
    'status',
    'storage_limit_token',
    'tenant_uuid',
    'total_containers',
  };
}

