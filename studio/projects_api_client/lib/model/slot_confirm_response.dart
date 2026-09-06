//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SlotConfirmResponse {
  /// Returns a new [SlotConfirmResponse] instance.
  SlotConfirmResponse({
    required this.apiKeysetVersion,
    required this.installationConfirmed,
    required this.keyId,
    required this.slotId,
  });

  int apiKeysetVersion;

  bool installationConfirmed;

  String keyId;

  String slotId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SlotConfirmResponse &&
    other.apiKeysetVersion == apiKeysetVersion &&
    other.installationConfirmed == installationConfirmed &&
    other.keyId == keyId &&
    other.slotId == slotId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (apiKeysetVersion.hashCode) +
    (installationConfirmed.hashCode) +
    (keyId.hashCode) +
    (slotId.hashCode);

  @override
  String toString() => 'SlotConfirmResponse[apiKeysetVersion=$apiKeysetVersion, installationConfirmed=$installationConfirmed, keyId=$keyId, slotId=$slotId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'api_keyset_version'] = this.apiKeysetVersion;
      json[r'installation_confirmed'] = this.installationConfirmed;
      json[r'key_id'] = this.keyId;
      json[r'slot_id'] = this.slotId;
    return json;
  }

  /// Returns a new [SlotConfirmResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SlotConfirmResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "SlotConfirmResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "SlotConfirmResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return SlotConfirmResponse(
        apiKeysetVersion: mapValueOfType<int>(json, r'api_keyset_version')!,
        installationConfirmed: mapValueOfType<bool>(json, r'installation_confirmed')!,
        keyId: mapValueOfType<String>(json, r'key_id')!,
        slotId: mapValueOfType<String>(json, r'slot_id')!,
      );
    }
    return null;
  }

  static List<SlotConfirmResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SlotConfirmResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SlotConfirmResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SlotConfirmResponse> mapFromJson(dynamic json) {
    final map = <String, SlotConfirmResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SlotConfirmResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SlotConfirmResponse-objects as value to a dart map
  static Map<String, List<SlotConfirmResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SlotConfirmResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SlotConfirmResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'api_keyset_version',
    'installation_confirmed',
    'key_id',
    'slot_id',
  };
}

