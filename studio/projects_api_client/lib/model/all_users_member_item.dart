//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AllUsersMemberItem {
  /// Returns a new [AllUsersMemberItem] instance.
  AllUsersMemberItem({
    required this.role,
    required this.status,
    required this.userId,
  });

  String role;

  String status;

  String userId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AllUsersMemberItem &&
    other.role == role &&
    other.status == status &&
    other.userId == userId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (role.hashCode) +
    (status.hashCode) +
    (userId.hashCode);

  @override
  String toString() => 'AllUsersMemberItem[role=$role, status=$status, userId=$userId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'role'] = this.role;
      json[r'status'] = this.status;
      json[r'user_id'] = this.userId;
    return json;
  }

  /// Returns a new [AllUsersMemberItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AllUsersMemberItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "AllUsersMemberItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "AllUsersMemberItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return AllUsersMemberItem(
        role: mapValueOfType<String>(json, r'role')!,
        status: mapValueOfType<String>(json, r'status')!,
        userId: mapValueOfType<String>(json, r'user_id')!,
      );
    }
    return null;
  }

  static List<AllUsersMemberItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AllUsersMemberItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AllUsersMemberItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AllUsersMemberItem> mapFromJson(dynamic json) {
    final map = <String, AllUsersMemberItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AllUsersMemberItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AllUsersMemberItem-objects as value to a dart map
  static Map<String, List<AllUsersMemberItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AllUsersMemberItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AllUsersMemberItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'role',
    'status',
    'user_id',
  };
}

