//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectNotificationRead {
  /// Returns a new [ProjectNotificationRead] instance.
  ProjectNotificationRead({
    this.read = true,
  });

  bool read;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectNotificationRead &&
    other.read == read;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (read.hashCode);

  @override
  String toString() => 'ProjectNotificationRead[read=$read]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'read'] = this.read;
    return json;
  }

  /// Returns a new [ProjectNotificationRead] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectNotificationRead? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return ProjectNotificationRead(
        read: mapValueOfType<bool>(json, r'read') ?? true,
      );
    }
    return null;
  }

  static List<ProjectNotificationRead> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectNotificationRead>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectNotificationRead.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectNotificationRead> mapFromJson(dynamic json) {
    final map = <String, ProjectNotificationRead>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectNotificationRead.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectNotificationRead-objects as value to a dart map
  static Map<String, List<ProjectNotificationRead>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectNotificationRead>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectNotificationRead.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
  };
}

