//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectHintCreate {
  /// Returns a new [ProjectHintCreate] instance.
  ProjectHintCreate({
    required this.body,
    required this.targetUserId,
  });

  String body;

  String targetUserId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectHintCreate &&
    other.body == body &&
    other.targetUserId == targetUserId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (body.hashCode) +
    (targetUserId.hashCode);

  @override
  String toString() => 'ProjectHintCreate[body=$body, targetUserId=$targetUserId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'body'] = this.body;
      json[r'target_user_id'] = this.targetUserId;
    return json;
  }

  /// Returns a new [ProjectHintCreate] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectHintCreate? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectHintCreate[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectHintCreate[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectHintCreate(
        body: mapValueOfType<String>(json, r'body')!,
        targetUserId: mapValueOfType<String>(json, r'target_user_id')!,
      );
    }
    return null;
  }

  static List<ProjectHintCreate> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectHintCreate>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectHintCreate.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectHintCreate> mapFromJson(dynamic json) {
    final map = <String, ProjectHintCreate>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectHintCreate.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectHintCreate-objects as value to a dart map
  static Map<String, List<ProjectHintCreate>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectHintCreate>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectHintCreate.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'body',
    'target_user_id',
  };
}

