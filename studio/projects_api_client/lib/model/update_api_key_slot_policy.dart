//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class UpdateApiKeySlotPolicy {
  /// Returns a new [UpdateApiKeySlotPolicy] instance.
  UpdateApiKeySlotPolicy({
    this.allowedServices,
    this.automaticRotationEnabled,
    this.rotationIntervalDays,
  });

  ///
  /// Please note: This property should have been non-nullable! Since the specification file
  /// does not include a default value (using the "default:" property), however, the generated
  /// source code must fall back to having a nullable type.
  /// Consider adding a "default:" property in the specification file to hide this note.
  ///
  AllowedServices? allowedServices;

  ///
  /// Please note: This property should have been non-nullable! Since the specification file
  /// does not include a default value (using the "default:" property), however, the generated
  /// source code must fall back to having a nullable type.
  /// Consider adding a "default:" property in the specification file to hide this note.
  ///
  AutomaticRotationEnabled? automaticRotationEnabled;

  ///
  /// Please note: This property should have been non-nullable! Since the specification file
  /// does not include a default value (using the "default:" property), however, the generated
  /// source code must fall back to having a nullable type.
  /// Consider adding a "default:" property in the specification file to hide this note.
  ///
  RotationIntervalDays1? rotationIntervalDays;

  @override
  bool operator ==(Object other) => identical(this, other) || other is UpdateApiKeySlotPolicy &&
    other.allowedServices == allowedServices &&
    other.automaticRotationEnabled == automaticRotationEnabled &&
    other.rotationIntervalDays == rotationIntervalDays;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (allowedServices == null ? 0 : allowedServices!.hashCode) +
    (automaticRotationEnabled == null ? 0 : automaticRotationEnabled!.hashCode) +
    (rotationIntervalDays == null ? 0 : rotationIntervalDays!.hashCode);

  @override
  String toString() => 'UpdateApiKeySlotPolicy[allowedServices=$allowedServices, automaticRotationEnabled=$automaticRotationEnabled, rotationIntervalDays=$rotationIntervalDays]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.allowedServices != null) {
      json[r'allowed_services'] = this.allowedServices;
    } else {
      json[r'allowed_services'] = null;
    }
    if (this.automaticRotationEnabled != null) {
      json[r'automatic_rotation_enabled'] = this.automaticRotationEnabled;
    } else {
      json[r'automatic_rotation_enabled'] = null;
    }
    if (this.rotationIntervalDays != null) {
      json[r'rotation_interval_days'] = this.rotationIntervalDays;
    } else {
      json[r'rotation_interval_days'] = null;
    }
    return json;
  }

  /// Returns a new [UpdateApiKeySlotPolicy] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static UpdateApiKeySlotPolicy? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "UpdateApiKeySlotPolicy[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "UpdateApiKeySlotPolicy[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return UpdateApiKeySlotPolicy(
        allowedServices: AllowedServices.fromJson(json[r'allowed_services']),
        automaticRotationEnabled: AutomaticRotationEnabled.fromJson(json[r'automatic_rotation_enabled']),
        rotationIntervalDays: RotationIntervalDays1.fromJson(json[r'rotation_interval_days']),
      );
    }
    return null;
  }

  static List<UpdateApiKeySlotPolicy> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <UpdateApiKeySlotPolicy>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = UpdateApiKeySlotPolicy.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, UpdateApiKeySlotPolicy> mapFromJson(dynamic json) {
    final map = <String, UpdateApiKeySlotPolicy>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = UpdateApiKeySlotPolicy.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of UpdateApiKeySlotPolicy-objects as value to a dart map
  static Map<String, List<UpdateApiKeySlotPolicy>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<UpdateApiKeySlotPolicy>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = UpdateApiKeySlotPolicy.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
  };
}

