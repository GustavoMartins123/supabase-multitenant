//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AddMember {
  /// Returns a new [AddMember] instance.
  AddMember({
    this.role = const AddMemberRoleEnum._('member'),
    required this.userId,
  });

  AddMemberRoleEnum role;

  String userId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AddMember &&
    other.role == role &&
    other.userId == userId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (role.hashCode) +
    (userId.hashCode);

  @override
  String toString() => 'AddMember[role=$role, userId=$userId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'role'] = this.role;
      json[r'user_id'] = this.userId;
    return json;
  }

  /// Returns a new [AddMember] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AddMember? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "AddMember[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "AddMember[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return AddMember(
        role: AddMemberRoleEnum.fromJson(json[r'role']) ?? const AddMemberRoleEnum._('member'),
        userId: mapValueOfType<String>(json, r'user_id')!,
      );
    }
    return null;
  }

  static List<AddMember> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AddMember>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AddMember.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AddMember> mapFromJson(dynamic json) {
    final map = <String, AddMember>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AddMember.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AddMember-objects as value to a dart map
  static Map<String, List<AddMember>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AddMember>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AddMember.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'user_id',
  };
}


class AddMemberRoleEnum {
  /// Instantiate a new enum with the provided [value].
  const AddMemberRoleEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const admin = AddMemberRoleEnum._(r'admin');
  static const member = AddMemberRoleEnum._(r'member');

  /// List of all possible values in this [enum][AddMemberRoleEnum].
  static const values = <AddMemberRoleEnum>[
    admin,
    member,
  ];

  static AddMemberRoleEnum? fromJson(dynamic value) => AddMemberRoleEnumTypeTransformer().decode(value);

  static List<AddMemberRoleEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AddMemberRoleEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AddMemberRoleEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [AddMemberRoleEnum] to String,
/// and [decode] dynamic data back to [AddMemberRoleEnum].
class AddMemberRoleEnumTypeTransformer {
  factory AddMemberRoleEnumTypeTransformer() => _instance ??= const AddMemberRoleEnumTypeTransformer._();

  const AddMemberRoleEnumTypeTransformer._();

  String encode(AddMemberRoleEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a AddMemberRoleEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  AddMemberRoleEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'admin': return AddMemberRoleEnum.admin;
        case r'member': return AddMemberRoleEnum.member;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [AddMemberRoleEnumTypeTransformer] instance.
  static AddMemberRoleEnumTypeTransformer? _instance;
}


