//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AvailableProjectUser {
  /// Returns a new [AvailableProjectUser] instance.
  AvailableProjectUser({
    required this.displayName,
    required this.isActive,
    required this.pictureUrl,
    required this.status,
    required this.userId,
    required this.username,
  });

  String displayName;

  bool isActive;

  String? pictureUrl;

  AvailableProjectUserStatusEnum status;

  String userId;

  String username;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AvailableProjectUser &&
    other.displayName == displayName &&
    other.isActive == isActive &&
    other.pictureUrl == pictureUrl &&
    other.status == status &&
    other.userId == userId &&
    other.username == username;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName.hashCode) +
    (isActive.hashCode) +
    (pictureUrl == null ? 0 : pictureUrl!.hashCode) +
    (status.hashCode) +
    (userId.hashCode) +
    (username.hashCode);

  @override
  String toString() => 'AvailableProjectUser[displayName=$displayName, isActive=$isActive, pictureUrl=$pictureUrl, status=$status, userId=$userId, username=$username]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'display_name'] = this.displayName;
      json[r'is_active'] = this.isActive;
    if (this.pictureUrl != null) {
      json[r'picture_url'] = this.pictureUrl;
    } else {
      json[r'picture_url'] = null;
    }
      json[r'status'] = this.status;
      json[r'user_id'] = this.userId;
      json[r'username'] = this.username;
    return json;
  }

  /// Returns a new [AvailableProjectUser] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AvailableProjectUser? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'picture_url'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return AvailableProjectUser(
        displayName: mapValueOfType<String>(json, r'display_name')!,
        isActive: mapValueOfType<bool>(json, r'is_active')!,
        pictureUrl: mapValueOfType<String>(json, r'picture_url'),
        status: AvailableProjectUserStatusEnum.fromJson(json[r'status'])!,
        userId: mapValueOfType<String>(json, r'user_id')!,
        username: mapValueOfType<String>(json, r'username')!,
      );
    }
    return null;
  }

  static List<AvailableProjectUser> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AvailableProjectUser>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AvailableProjectUser.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AvailableProjectUser> mapFromJson(dynamic json) {
    final map = <String, AvailableProjectUser>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AvailableProjectUser.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AvailableProjectUser-objects as value to a dart map
  static Map<String, List<AvailableProjectUser>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AvailableProjectUser>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AvailableProjectUser.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'display_name',
    'is_active',
    'picture_url',
    'status',
    'user_id',
    'username',
  };
}


class AvailableProjectUserStatusEnum {
  /// Instantiate a new enum with the provided [value].
  const AvailableProjectUserStatusEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const active = AvailableProjectUserStatusEnum._(r'active');
  static const member = AvailableProjectUserStatusEnum._(r'member');
  static const available = AvailableProjectUserStatusEnum._(r'available');

  /// List of all possible values in this [enum][AvailableProjectUserStatusEnum].
  static const values = <AvailableProjectUserStatusEnum>[
    active,
    member,
    available,
  ];

  static AvailableProjectUserStatusEnum? fromJson(dynamic value) => AvailableProjectUserStatusEnumTypeTransformer().decode(value);

  static List<AvailableProjectUserStatusEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AvailableProjectUserStatusEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AvailableProjectUserStatusEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [AvailableProjectUserStatusEnum] to String,
/// and [decode] dynamic data back to [AvailableProjectUserStatusEnum].
class AvailableProjectUserStatusEnumTypeTransformer {
  factory AvailableProjectUserStatusEnumTypeTransformer() => _instance ??= const AvailableProjectUserStatusEnumTypeTransformer._();

  const AvailableProjectUserStatusEnumTypeTransformer._();

  String encode(AvailableProjectUserStatusEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a AvailableProjectUserStatusEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  AvailableProjectUserStatusEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'active': return AvailableProjectUserStatusEnum.active;
        case r'member': return AvailableProjectUserStatusEnum.member;
        case r'available': return AvailableProjectUserStatusEnum.available;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [AvailableProjectUserStatusEnumTypeTransformer] instance.
  static AvailableProjectUserStatusEnumTypeTransformer? _instance;
}


