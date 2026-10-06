//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class PrivilegeChangeBody {
  /// Returns a new [PrivilegeChangeBody] instance.
  PrivilegeChangeBody({
    required this.execution,
    required this.label,
    required this.operation,
    required this.permission,
    this.privileges = const [],
    required this.role,
    this.tables = const [],
  });

  PrivilegeExecution execution;

  String label;

  PrivilegeChangeBodyOperationEnum operation;

  String permission;

  List<PrivilegeChangeBodyPrivilegesEnum> privileges;

  PrivilegeChangeBodyRoleEnum role;

  List<String> tables;

  @override
  bool operator ==(Object other) => identical(this, other) || other is PrivilegeChangeBody &&
    other.execution == execution &&
    other.label == label &&
    other.operation == operation &&
    other.permission == permission &&
    _deepEquality.equals(other.privileges, privileges) &&
    other.role == role &&
    _deepEquality.equals(other.tables, tables);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (execution.hashCode) +
    (label.hashCode) +
    (operation.hashCode) +
    (permission.hashCode) +
    (privileges.hashCode) +
    (role.hashCode) +
    (tables.hashCode);

  @override
  String toString() => 'PrivilegeChangeBody[execution=$execution, label=$label, operation=$operation, permission=$permission, privileges=$privileges, role=$role, tables=$tables]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'execution'] = this.execution;
      json[r'label'] = this.label;
      json[r'operation'] = this.operation;
      json[r'permission'] = this.permission;
      json[r'privileges'] = this.privileges;
      json[r'role'] = this.role;
      json[r'tables'] = this.tables;
    return json;
  }

  /// Returns a new [PrivilegeChangeBody] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static PrivilegeChangeBody? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return PrivilegeChangeBody(
        execution: PrivilegeExecution.fromJson(json[r'execution'])!,
        label: mapValueOfType<String>(json, r'label')!,
        operation: PrivilegeChangeBodyOperationEnum.fromJson(json[r'operation'])!,
        permission: mapValueOfType<String>(json, r'permission')!,
        privileges: PrivilegeChangeBodyPrivilegesEnum.listFromJson(json[r'privileges']),
        role: PrivilegeChangeBodyRoleEnum.fromJson(json[r'role'])!,
        tables: json[r'tables'] is Iterable
            ? (json[r'tables'] as Iterable).cast<String>().toList(growable: false)
            : const [],
      );
    }
    return null;
  }

  static List<PrivilegeChangeBody> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PrivilegeChangeBody>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PrivilegeChangeBody.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, PrivilegeChangeBody> mapFromJson(dynamic json) {
    final map = <String, PrivilegeChangeBody>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = PrivilegeChangeBody.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of PrivilegeChangeBody-objects as value to a dart map
  static Map<String, List<PrivilegeChangeBody>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<PrivilegeChangeBody>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = PrivilegeChangeBody.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'execution',
    'label',
    'operation',
    'permission',
    'privileges',
    'role',
    'tables',
  };
}


class PrivilegeChangeBodyOperationEnum {
  /// Instantiate a new enum with the provided [value].
  const PrivilegeChangeBodyOperationEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const grant = PrivilegeChangeBodyOperationEnum._(r'grant');
  static const revoke = PrivilegeChangeBodyOperationEnum._(r'revoke');

  /// List of all possible values in this [enum][PrivilegeChangeBodyOperationEnum].
  static const values = <PrivilegeChangeBodyOperationEnum>[
    grant,
    revoke,
  ];

  static PrivilegeChangeBodyOperationEnum? fromJson(dynamic value) => PrivilegeChangeBodyOperationEnumTypeTransformer().decode(value);

  static List<PrivilegeChangeBodyOperationEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PrivilegeChangeBodyOperationEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PrivilegeChangeBodyOperationEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [PrivilegeChangeBodyOperationEnum] to String,
/// and [decode] dynamic data back to [PrivilegeChangeBodyOperationEnum].
class PrivilegeChangeBodyOperationEnumTypeTransformer {
  factory PrivilegeChangeBodyOperationEnumTypeTransformer() => _instance ??= const PrivilegeChangeBodyOperationEnumTypeTransformer._();

  const PrivilegeChangeBodyOperationEnumTypeTransformer._();

  String encode(PrivilegeChangeBodyOperationEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a PrivilegeChangeBodyOperationEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  PrivilegeChangeBodyOperationEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'grant': return PrivilegeChangeBodyOperationEnum.grant;
        case r'revoke': return PrivilegeChangeBodyOperationEnum.revoke;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [PrivilegeChangeBodyOperationEnumTypeTransformer] instance.
  static PrivilegeChangeBodyOperationEnumTypeTransformer? _instance;
}



class PrivilegeChangeBodyPrivilegesEnum {
  /// Instantiate a new enum with the provided [value].
  const PrivilegeChangeBodyPrivilegesEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const SELECT = PrivilegeChangeBodyPrivilegesEnum._(r'SELECT');
  static const INSERT = PrivilegeChangeBodyPrivilegesEnum._(r'INSERT');
  static const UPDATE = PrivilegeChangeBodyPrivilegesEnum._(r'UPDATE');
  static const DELETE = PrivilegeChangeBodyPrivilegesEnum._(r'DELETE');

  /// List of all possible values in this [enum][PrivilegeChangeBodyPrivilegesEnum].
  static const values = <PrivilegeChangeBodyPrivilegesEnum>[
    SELECT,
    INSERT,
    UPDATE,
    DELETE,
  ];

  static PrivilegeChangeBodyPrivilegesEnum? fromJson(dynamic value) => PrivilegeChangeBodyPrivilegesEnumTypeTransformer().decode(value);

  static List<PrivilegeChangeBodyPrivilegesEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PrivilegeChangeBodyPrivilegesEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PrivilegeChangeBodyPrivilegesEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [PrivilegeChangeBodyPrivilegesEnum] to String,
/// and [decode] dynamic data back to [PrivilegeChangeBodyPrivilegesEnum].
class PrivilegeChangeBodyPrivilegesEnumTypeTransformer {
  factory PrivilegeChangeBodyPrivilegesEnumTypeTransformer() => _instance ??= const PrivilegeChangeBodyPrivilegesEnumTypeTransformer._();

  const PrivilegeChangeBodyPrivilegesEnumTypeTransformer._();

  String encode(PrivilegeChangeBodyPrivilegesEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a PrivilegeChangeBodyPrivilegesEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  PrivilegeChangeBodyPrivilegesEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'SELECT': return PrivilegeChangeBodyPrivilegesEnum.SELECT;
        case r'INSERT': return PrivilegeChangeBodyPrivilegesEnum.INSERT;
        case r'UPDATE': return PrivilegeChangeBodyPrivilegesEnum.UPDATE;
        case r'DELETE': return PrivilegeChangeBodyPrivilegesEnum.DELETE;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [PrivilegeChangeBodyPrivilegesEnumTypeTransformer] instance.
  static PrivilegeChangeBodyPrivilegesEnumTypeTransformer? _instance;
}



class PrivilegeChangeBodyRoleEnum {
  /// Instantiate a new enum with the provided [value].
  const PrivilegeChangeBodyRoleEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const anon = PrivilegeChangeBodyRoleEnum._(r'anon');
  static const authenticated = PrivilegeChangeBodyRoleEnum._(r'authenticated');

  /// List of all possible values in this [enum][PrivilegeChangeBodyRoleEnum].
  static const values = <PrivilegeChangeBodyRoleEnum>[
    anon,
    authenticated,
  ];

  static PrivilegeChangeBodyRoleEnum? fromJson(dynamic value) => PrivilegeChangeBodyRoleEnumTypeTransformer().decode(value);

  static List<PrivilegeChangeBodyRoleEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PrivilegeChangeBodyRoleEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PrivilegeChangeBodyRoleEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [PrivilegeChangeBodyRoleEnum] to String,
/// and [decode] dynamic data back to [PrivilegeChangeBodyRoleEnum].
class PrivilegeChangeBodyRoleEnumTypeTransformer {
  factory PrivilegeChangeBodyRoleEnumTypeTransformer() => _instance ??= const PrivilegeChangeBodyRoleEnumTypeTransformer._();

  const PrivilegeChangeBodyRoleEnumTypeTransformer._();

  String encode(PrivilegeChangeBodyRoleEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a PrivilegeChangeBodyRoleEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  PrivilegeChangeBodyRoleEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'anon': return PrivilegeChangeBodyRoleEnum.anon;
        case r'authenticated': return PrivilegeChangeBodyRoleEnum.authenticated;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [PrivilegeChangeBodyRoleEnumTypeTransformer] instance.
  static PrivilegeChangeBodyRoleEnumTypeTransformer? _instance;
}


