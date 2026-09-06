//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class MemberItem {
  /// Returns a new [MemberItem] instance.
  MemberItem({
    required this.role,
    required this.userId,
  });

  String role;

  String userId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is MemberItem &&
    other.role == role &&
    other.userId == userId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (role.hashCode) +
    (userId.hashCode);

  @override
  String toString() => 'MemberItem[role=$role, userId=$userId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'role'] = this.role;
      json[r'user_id'] = this.userId;
    return json;
  }

  /// Returns a new [MemberItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static MemberItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "MemberItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "MemberItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return MemberItem(
        role: mapValueOfType<String>(json, r'role')!,
        userId: mapValueOfType<String>(json, r'user_id')!,
      );
    }
    return null;
  }

  static List<MemberItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <MemberItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = MemberItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, MemberItem> mapFromJson(dynamic json) {
    final map = <String, MemberItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = MemberItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of MemberItem-objects as value to a dart map
  static Map<String, List<MemberItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<MemberItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = MemberItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'role',
    'user_id',
  };
}

