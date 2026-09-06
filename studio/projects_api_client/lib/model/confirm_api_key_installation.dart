//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ConfirmApiKeyInstallation {
  /// Returns a new [ConfirmApiKeyInstallation] instance.
  ConfirmApiKeyInstallation({
    required this.keyId,
  });

  String keyId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ConfirmApiKeyInstallation &&
    other.keyId == keyId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (keyId.hashCode);

  @override
  String toString() => 'ConfirmApiKeyInstallation[keyId=$keyId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'key_id'] = this.keyId;
    return json;
  }

  /// Returns a new [ConfirmApiKeyInstallation] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ConfirmApiKeyInstallation? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ConfirmApiKeyInstallation[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ConfirmApiKeyInstallation[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ConfirmApiKeyInstallation(
        keyId: mapValueOfType<String>(json, r'key_id')!,
      );
    }
    return null;
  }

  static List<ConfirmApiKeyInstallation> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ConfirmApiKeyInstallation>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ConfirmApiKeyInstallation.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ConfirmApiKeyInstallation> mapFromJson(dynamic json) {
    final map = <String, ConfirmApiKeyInstallation>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ConfirmApiKeyInstallation.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ConfirmApiKeyInstallation-objects as value to a dart map
  static Map<String, List<ConfirmApiKeyInstallation>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ConfirmApiKeyInstallation>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ConfirmApiKeyInstallation.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'key_id',
  };
}

