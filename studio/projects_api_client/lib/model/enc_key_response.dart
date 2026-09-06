//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class EncKeyResponse {
  /// Returns a new [EncKeyResponse] instance.
  EncKeyResponse({
    required this.encServiceKey,
    required this.projectKeyVersion,
  });

  String encServiceKey;

  int? projectKeyVersion;

  @override
  bool operator ==(Object other) => identical(this, other) || other is EncKeyResponse &&
    other.encServiceKey == encServiceKey &&
    other.projectKeyVersion == projectKeyVersion;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (encServiceKey.hashCode) +
    (projectKeyVersion == null ? 0 : projectKeyVersion!.hashCode);

  @override
  String toString() => 'EncKeyResponse[encServiceKey=$encServiceKey, projectKeyVersion=$projectKeyVersion]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'enc_service_key'] = this.encServiceKey;
    if (this.projectKeyVersion != null) {
      json[r'project_key_version'] = this.projectKeyVersion;
    } else {
      json[r'project_key_version'] = null;
    }
    return json;
  }

  /// Returns a new [EncKeyResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static EncKeyResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "EncKeyResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "EncKeyResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return EncKeyResponse(
        encServiceKey: mapValueOfType<String>(json, r'enc_service_key')!,
        projectKeyVersion: mapValueOfType<int>(json, r'project_key_version'),
      );
    }
    return null;
  }

  static List<EncKeyResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <EncKeyResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = EncKeyResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, EncKeyResponse> mapFromJson(dynamic json) {
    final map = <String, EncKeyResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = EncKeyResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of EncKeyResponse-objects as value to a dart map
  static Map<String, List<EncKeyResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<EncKeyResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = EncKeyResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'enc_service_key',
    'project_key_version',
  };
}

