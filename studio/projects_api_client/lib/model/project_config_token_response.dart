//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectConfigTokenResponse {
  /// Returns a new [ProjectConfigTokenResponse] instance.
  ProjectConfigTokenResponse({
    required this.configToken,
    required this.project,
  });

  String configToken;

  String project;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectConfigTokenResponse &&
    other.configToken == configToken &&
    other.project == project;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (configToken.hashCode) +
    (project.hashCode);

  @override
  String toString() => 'ProjectConfigTokenResponse[configToken=$configToken, project=$project]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'config_token'] = this.configToken;
      json[r'project'] = this.project;
    return json;
  }

  /// Returns a new [ProjectConfigTokenResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectConfigTokenResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectConfigTokenResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectConfigTokenResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectConfigTokenResponse(
        configToken: mapValueOfType<String>(json, r'config_token')!,
        project: mapValueOfType<String>(json, r'project')!,
      );
    }
    return null;
  }

  static List<ProjectConfigTokenResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectConfigTokenResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectConfigTokenResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectConfigTokenResponse> mapFromJson(dynamic json) {
    final map = <String, ProjectConfigTokenResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectConfigTokenResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectConfigTokenResponse-objects as value to a dart map
  static Map<String, List<ProjectConfigTokenResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectConfigTokenResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectConfigTokenResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'config_token',
    'project',
  };
}

