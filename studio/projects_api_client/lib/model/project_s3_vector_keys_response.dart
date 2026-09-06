//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectS3VectorKeysResponse {
  /// Returns a new [ProjectS3VectorKeysResponse] instance.
  ProjectS3VectorKeysResponse({
    required this.accessKey,
    required this.secretKey,
  });

  String accessKey;

  String secretKey;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectS3VectorKeysResponse &&
    other.accessKey == accessKey &&
    other.secretKey == secretKey;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (accessKey.hashCode) +
    (secretKey.hashCode);

  @override
  String toString() => 'ProjectS3VectorKeysResponse[accessKey=$accessKey, secretKey=$secretKey]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'accessKey'] = this.accessKey;
      json[r'secretKey'] = this.secretKey;
    return json;
  }

  /// Returns a new [ProjectS3VectorKeysResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectS3VectorKeysResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectS3VectorKeysResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectS3VectorKeysResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectS3VectorKeysResponse(
        accessKey: mapValueOfType<String>(json, r'accessKey')!,
        secretKey: mapValueOfType<String>(json, r'secretKey')!,
      );
    }
    return null;
  }

  static List<ProjectS3VectorKeysResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectS3VectorKeysResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectS3VectorKeysResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectS3VectorKeysResponse> mapFromJson(dynamic json) {
    final map = <String, ProjectS3VectorKeysResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectS3VectorKeysResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectS3VectorKeysResponse-objects as value to a dart map
  static Map<String, List<ProjectS3VectorKeysResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectS3VectorKeysResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectS3VectorKeysResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'accessKey',
    'secretKey',
  };
}

