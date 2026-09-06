//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class UpdateProjectSettingsResponse {
  /// Returns a new [UpdateProjectSettingsResponse] instance.
  UpdateProjectSettingsResponse({
    this.affectedServices = const [],
    required this.fileSizeLimit,
    required this.message,
    required this.status,
    required this.storageLimitToken,
    this.updatedKeys = const [],
  });

  List<String> affectedServices;

  String fileSizeLimit;

  String message;

  String status;

  String storageLimitToken;

  List<String> updatedKeys;

  @override
  bool operator ==(Object other) => identical(this, other) || other is UpdateProjectSettingsResponse &&
    _deepEquality.equals(other.affectedServices, affectedServices) &&
    other.fileSizeLimit == fileSizeLimit &&
    other.message == message &&
    other.status == status &&
    other.storageLimitToken == storageLimitToken &&
    _deepEquality.equals(other.updatedKeys, updatedKeys);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (affectedServices.hashCode) +
    (fileSizeLimit.hashCode) +
    (message.hashCode) +
    (status.hashCode) +
    (storageLimitToken.hashCode) +
    (updatedKeys.hashCode);

  @override
  String toString() => 'UpdateProjectSettingsResponse[affectedServices=$affectedServices, fileSizeLimit=$fileSizeLimit, message=$message, status=$status, storageLimitToken=$storageLimitToken, updatedKeys=$updatedKeys]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'affected_services'] = this.affectedServices;
      json[r'file_size_limit'] = this.fileSizeLimit;
      json[r'message'] = this.message;
      json[r'status'] = this.status;
      json[r'storage_limit_token'] = this.storageLimitToken;
      json[r'updated_keys'] = this.updatedKeys;
    return json;
  }

  /// Returns a new [UpdateProjectSettingsResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static UpdateProjectSettingsResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "UpdateProjectSettingsResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "UpdateProjectSettingsResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return UpdateProjectSettingsResponse(
        affectedServices: json[r'affected_services'] is Iterable
            ? (json[r'affected_services'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        fileSizeLimit: mapValueOfType<String>(json, r'file_size_limit')!,
        message: mapValueOfType<String>(json, r'message')!,
        status: mapValueOfType<String>(json, r'status')!,
        storageLimitToken: mapValueOfType<String>(json, r'storage_limit_token')!,
        updatedKeys: json[r'updated_keys'] is Iterable
            ? (json[r'updated_keys'] as Iterable).cast<String>().toList(growable: false)
            : const [],
      );
    }
    return null;
  }

  static List<UpdateProjectSettingsResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <UpdateProjectSettingsResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = UpdateProjectSettingsResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, UpdateProjectSettingsResponse> mapFromJson(dynamic json) {
    final map = <String, UpdateProjectSettingsResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = UpdateProjectSettingsResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of UpdateProjectSettingsResponse-objects as value to a dart map
  static Map<String, List<UpdateProjectSettingsResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<UpdateProjectSettingsResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = UpdateProjectSettingsResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'affected_services',
    'file_size_limit',
    'message',
    'status',
    'storage_limit_token',
    'updated_keys',
  };
}

