//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectRenameRequest {
  /// Returns a new [ProjectRenameRequest] instance.
  ProjectRenameRequest({
    this.displayName,
    required this.newName,
  });

  String? displayName;

  String newName;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectRenameRequest &&
    other.displayName == displayName &&
    other.newName == newName;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName == null ? 0 : displayName!.hashCode) +
    (newName.hashCode);

  @override
  String toString() => 'ProjectRenameRequest[displayName=$displayName, newName=$newName]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.displayName != null) {
      json[r'display_name'] = this.displayName;
    } else {
      json[r'display_name'] = null;
    }
      json[r'new_name'] = this.newName;
    return json;
  }

  /// Returns a new [ProjectRenameRequest] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectRenameRequest? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectRenameRequest[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectRenameRequest[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectRenameRequest(
        displayName: mapValueOfType<String>(json, r'display_name'),
        newName: mapValueOfType<String>(json, r'new_name')!,
      );
    }
    return null;
  }

  static List<ProjectRenameRequest> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectRenameRequest>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectRenameRequest.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectRenameRequest> mapFromJson(dynamic json) {
    final map = <String, ProjectRenameRequest>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectRenameRequest.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectRenameRequest-objects as value to a dart map
  static Map<String, List<ProjectRenameRequest>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectRenameRequest>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectRenameRequest.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'new_name',
  };
}

