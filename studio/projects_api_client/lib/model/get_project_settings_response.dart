//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class GetProjectSettingsResponse {
  /// Returns a new [GetProjectSettingsResponse] instance.
  GetProjectSettingsResponse({
    this.pendingAffectedServices = const [],
    this.settings = const {},
    required this.storageLimitToken,
  });

  List<String> pendingAffectedServices;

  Map<String, String> settings;

  String? storageLimitToken;

  @override
  bool operator ==(Object other) => identical(this, other) || other is GetProjectSettingsResponse &&
    _deepEquality.equals(other.pendingAffectedServices, pendingAffectedServices) &&
    _deepEquality.equals(other.settings, settings) &&
    other.storageLimitToken == storageLimitToken;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (pendingAffectedServices.hashCode) +
    (settings.hashCode) +
    (storageLimitToken == null ? 0 : storageLimitToken!.hashCode);

  @override
  String toString() => 'GetProjectSettingsResponse[pendingAffectedServices=$pendingAffectedServices, settings=$settings, storageLimitToken=$storageLimitToken]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'pending_affected_services'] = this.pendingAffectedServices;
      json[r'settings'] = this.settings;
    if (this.storageLimitToken != null) {
      json[r'storage_limit_token'] = this.storageLimitToken;
    } else {
      json[r'storage_limit_token'] = null;
    }
    return json;
  }

  /// Returns a new [GetProjectSettingsResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static GetProjectSettingsResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "GetProjectSettingsResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "GetProjectSettingsResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return GetProjectSettingsResponse(
        pendingAffectedServices: json[r'pending_affected_services'] is Iterable
            ? (json[r'pending_affected_services'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        settings: mapCastOfType<String, String>(json, r'settings')!,
        storageLimitToken: mapValueOfType<String>(json, r'storage_limit_token'),
      );
    }
    return null;
  }

  static List<GetProjectSettingsResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <GetProjectSettingsResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = GetProjectSettingsResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, GetProjectSettingsResponse> mapFromJson(dynamic json) {
    final map = <String, GetProjectSettingsResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = GetProjectSettingsResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of GetProjectSettingsResponse-objects as value to a dart map
  static Map<String, List<GetProjectSettingsResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<GetProjectSettingsResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = GetProjectSettingsResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'pending_affected_services',
    'settings',
    'storage_limit_token',
  };
}

