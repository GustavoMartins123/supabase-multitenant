//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RestorePointsPermissions {
  /// Returns a new [RestorePointsPermissions] instance.
  RestorePointsPermissions({
    required this.canCreate,
    required this.canDelete,
    required this.canRestore,
  });

  bool canCreate;

  bool canDelete;

  bool canRestore;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RestorePointsPermissions &&
    other.canCreate == canCreate &&
    other.canDelete == canDelete &&
    other.canRestore == canRestore;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (canCreate.hashCode) +
    (canDelete.hashCode) +
    (canRestore.hashCode);

  @override
  String toString() => 'RestorePointsPermissions[canCreate=$canCreate, canDelete=$canDelete, canRestore=$canRestore]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'can_create'] = this.canCreate;
      json[r'can_delete'] = this.canDelete;
      json[r'can_restore'] = this.canRestore;
    return json;
  }

  /// Returns a new [RestorePointsPermissions] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RestorePointsPermissions? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RestorePointsPermissions[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RestorePointsPermissions[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RestorePointsPermissions(
        canCreate: mapValueOfType<bool>(json, r'can_create')!,
        canDelete: mapValueOfType<bool>(json, r'can_delete')!,
        canRestore: mapValueOfType<bool>(json, r'can_restore')!,
      );
    }
    return null;
  }

  static List<RestorePointsPermissions> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RestorePointsPermissions>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RestorePointsPermissions.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RestorePointsPermissions> mapFromJson(dynamic json) {
    final map = <String, RestorePointsPermissions>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RestorePointsPermissions.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RestorePointsPermissions-objects as value to a dart map
  static Map<String, List<RestorePointsPermissions>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RestorePointsPermissions>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RestorePointsPermissions.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'can_create',
    'can_delete',
    'can_restore',
  };
}

