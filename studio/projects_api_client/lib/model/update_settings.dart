//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class UpdateSettings {
  /// Returns a new [UpdateSettings] instance.
  UpdateSettings({
    this.settings = const {},
  });

  Map<String, String> settings;

  @override
  bool operator ==(Object other) => identical(this, other) || other is UpdateSettings &&
    _deepEquality.equals(other.settings, settings);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (settings.hashCode);

  @override
  String toString() => 'UpdateSettings[settings=$settings]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'settings'] = this.settings;
    return json;
  }

  /// Returns a new [UpdateSettings] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static UpdateSettings? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "UpdateSettings[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "UpdateSettings[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return UpdateSettings(
        settings: mapCastOfType<String, String>(json, r'settings')!,
      );
    }
    return null;
  }

  static List<UpdateSettings> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <UpdateSettings>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = UpdateSettings.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, UpdateSettings> mapFromJson(dynamic json) {
    final map = <String, UpdateSettings>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = UpdateSettings.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of UpdateSettings-objects as value to a dart map
  static Map<String, List<UpdateSettings>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<UpdateSettings>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = UpdateSettings.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'settings',
  };
}

