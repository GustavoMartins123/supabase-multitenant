//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RevealClaimResponse {
  /// Returns a new [RevealClaimResponse] instance.
  RevealClaimResponse({
    required this.apiKey,
    required this.keyId,
  });

  String apiKey;

  String keyId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RevealClaimResponse &&
    other.apiKey == apiKey &&
    other.keyId == keyId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (apiKey.hashCode) +
    (keyId.hashCode);

  @override
  String toString() => 'RevealClaimResponse[apiKey=$apiKey, keyId=$keyId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'api_key'] = this.apiKey;
      json[r'key_id'] = this.keyId;
    return json;
  }

  /// Returns a new [RevealClaimResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RevealClaimResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RevealClaimResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RevealClaimResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RevealClaimResponse(
        apiKey: mapValueOfType<String>(json, r'api_key')!,
        keyId: mapValueOfType<String>(json, r'key_id')!,
      );
    }
    return null;
  }

  static List<RevealClaimResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RevealClaimResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RevealClaimResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RevealClaimResponse> mapFromJson(dynamic json) {
    final map = <String, RevealClaimResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RevealClaimResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RevealClaimResponse-objects as value to a dart map
  static Map<String, List<RevealClaimResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RevealClaimResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RevealClaimResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'api_key',
    'key_id',
  };
}

