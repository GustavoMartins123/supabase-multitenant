//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class MigrationCutoverResponse {
  /// Returns a new [MigrationCutoverResponse] instance.
  MigrationCutoverResponse({
    required this.apiKeysetVersion,
    required this.gatewayMode,
    required this.project,
    required this.status,
  });

  int apiKeysetVersion;

  String gatewayMode;

  String project;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is MigrationCutoverResponse &&
    other.apiKeysetVersion == apiKeysetVersion &&
    other.gatewayMode == gatewayMode &&
    other.project == project &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (apiKeysetVersion.hashCode) +
    (gatewayMode.hashCode) +
    (project.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'MigrationCutoverResponse[apiKeysetVersion=$apiKeysetVersion, gatewayMode=$gatewayMode, project=$project, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'api_keyset_version'] = this.apiKeysetVersion;
      json[r'gateway_mode'] = this.gatewayMode;
      json[r'project'] = this.project;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [MigrationCutoverResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static MigrationCutoverResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "MigrationCutoverResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "MigrationCutoverResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return MigrationCutoverResponse(
        apiKeysetVersion: mapValueOfType<int>(json, r'api_keyset_version')!,
        gatewayMode: mapValueOfType<String>(json, r'gateway_mode')!,
        project: mapValueOfType<String>(json, r'project')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<MigrationCutoverResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <MigrationCutoverResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = MigrationCutoverResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, MigrationCutoverResponse> mapFromJson(dynamic json) {
    final map = <String, MigrationCutoverResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = MigrationCutoverResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of MigrationCutoverResponse-objects as value to a dart map
  static Map<String, List<MigrationCutoverResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<MigrationCutoverResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = MigrationCutoverResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'api_keyset_version',
    'gateway_mode',
    'project',
    'status',
  };
}

