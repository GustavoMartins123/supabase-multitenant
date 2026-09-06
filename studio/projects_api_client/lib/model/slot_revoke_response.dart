//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SlotRevokeResponse {
  /// Returns a new [SlotRevokeResponse] instance.
  SlotRevokeResponse({
    required this.apiKeysetVersion,
    required this.slotId,
    required this.status,
  });

  int apiKeysetVersion;

  String slotId;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SlotRevokeResponse &&
    other.apiKeysetVersion == apiKeysetVersion &&
    other.slotId == slotId &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (apiKeysetVersion.hashCode) +
    (slotId.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'SlotRevokeResponse[apiKeysetVersion=$apiKeysetVersion, slotId=$slotId, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'api_keyset_version'] = this.apiKeysetVersion;
      json[r'slot_id'] = this.slotId;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [SlotRevokeResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SlotRevokeResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "SlotRevokeResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "SlotRevokeResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return SlotRevokeResponse(
        apiKeysetVersion: mapValueOfType<int>(json, r'api_keyset_version')!,
        slotId: mapValueOfType<String>(json, r'slot_id')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<SlotRevokeResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SlotRevokeResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SlotRevokeResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SlotRevokeResponse> mapFromJson(dynamic json) {
    final map = <String, SlotRevokeResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SlotRevokeResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SlotRevokeResponse-objects as value to a dart map
  static Map<String, List<SlotRevokeResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SlotRevokeResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SlotRevokeResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'api_keyset_version',
    'slot_id',
    'status',
  };
}

