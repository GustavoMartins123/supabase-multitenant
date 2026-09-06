//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CollaborationMemberItem {
  /// Returns a new [CollaborationMemberItem] instance.
  CollaborationMemberItem({
    required this.displayName,
    required this.id,
    required this.role,
    required this.username,
  });

  String displayName;

  String id;

  String role;

  String username;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CollaborationMemberItem &&
    other.displayName == displayName &&
    other.id == id &&
    other.role == role &&
    other.username == username;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName.hashCode) +
    (id.hashCode) +
    (role.hashCode) +
    (username.hashCode);

  @override
  String toString() => 'CollaborationMemberItem[displayName=$displayName, id=$id, role=$role, username=$username]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'display_name'] = this.displayName;
      json[r'id'] = this.id;
      json[r'role'] = this.role;
      json[r'username'] = this.username;
    return json;
  }

  /// Returns a new [CollaborationMemberItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CollaborationMemberItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CollaborationMemberItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CollaborationMemberItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CollaborationMemberItem(
        displayName: mapValueOfType<String>(json, r'display_name')!,
        id: mapValueOfType<String>(json, r'id')!,
        role: mapValueOfType<String>(json, r'role')!,
        username: mapValueOfType<String>(json, r'username')!,
      );
    }
    return null;
  }

  static List<CollaborationMemberItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CollaborationMemberItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CollaborationMemberItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CollaborationMemberItem> mapFromJson(dynamic json) {
    final map = <String, CollaborationMemberItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CollaborationMemberItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CollaborationMemberItem-objects as value to a dart map
  static Map<String, List<CollaborationMemberItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CollaborationMemberItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CollaborationMemberItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'display_name',
    'id',
    'role',
    'username',
  };
}

