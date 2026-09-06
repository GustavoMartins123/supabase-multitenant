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
    required this.name,
    required this.runningContainers,
    required this.status,
    required this.storageLimitToken,
    required this.totalContainers,
  });

  String? displayName;

  String fileSizeLimit;

  String name;

  int runningContainers;

  String status;

  String storageLimitToken;

  int totalContainers;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectInfoItem &&
    other.displayName == displayName &&
    other.fileSizeLimit == fileSizeLimit &&
    other.name == name &&
    other.runningContainers == runningContainers &&
    other.status == status &&
    other.storageLimitToken == storageLimitToken &&
    other.totalContainers == totalContainers;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName == null ? 0 : displayName!.hashCode) +
    (fileSizeLimit.hashCode) +
    (name.hashCode) +
    (runningContainers.hashCode) +
    (status.hashCode) +
    (storageLimitToken.hashCode) +
    (totalContainers.hashCode);

  @override
  String toString() => 'ProjectInfoItem[displayName=$displayName, fileSizeLimit=$fileSizeLimit, name=$name, runningContainers=$runningContainers, status=$status, storageLimitToken=$storageLimitToken, totalContainers=$totalContainers]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.displayName != null) {
      json[r'display_name'] = this.displayName;
    } else {
      json[r'display_name'] = null;
    }
      json[r'file_size_limit'] = this.fileSizeLimit;
      json[r'name'] = this.name;
      json[r'running_containers'] = this.runningContainers;
      json[r'status'] = this.status;
      json[r'storage_limit_token'] = this.storageLimitToken;
      json[r'total_containers'] = this.totalContainers;
    return json;
  }

  /// Returns a new [ProjectInfoItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectInfoItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectInfoItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectInfoItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectInfoItem(
        displayName: mapValueOfType<String>(json, r'display_name'),
        fileSizeLimit: mapValueOfType<String>(json, r'file_size_limit')!,
        name: mapValueOfType<String>(json, r'name')!,
        runningContainers: mapValueOfType<int>(json, r'running_containers')!,
        status: mapValueOfType<String>(json, r'status')!,
        storageLimitToken: mapValueOfType<String>(json, r'storage_limit_token')!,
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
    'name',
    'running_containers',
    'status',
    'storage_limit_token',
    'total_containers',
  };
}

