//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AccessUsageRow {
  /// Returns a new [AccessUsageRow] instance.
  AccessUsageRow({
    required this.admitted,
    required this.period,
    required this.periodEnd,
    required this.periodStart,
    required this.scopeId,
    required this.scopeType,
  });

  int admitted;

  AccessUsageRowPeriodEnum period;

  DateTime periodEnd;

  DateTime periodStart;

  String scopeId;

  AccessUsageRowScopeTypeEnum scopeType;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AccessUsageRow &&
    other.admitted == admitted &&
    other.period == period &&
    other.periodEnd == periodEnd &&
    other.periodStart == periodStart &&
    other.scopeId == scopeId &&
    other.scopeType == scopeType;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (admitted.hashCode) +
    (period.hashCode) +
    (periodEnd.hashCode) +
    (periodStart.hashCode) +
    (scopeId.hashCode) +
    (scopeType.hashCode);

  @override
  String toString() => 'AccessUsageRow[admitted=$admitted, period=$period, periodEnd=$periodEnd, periodStart=$periodStart, scopeId=$scopeId, scopeType=$scopeType]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'admitted'] = this.admitted;
      json[r'period'] = this.period;
      json[r'period_end'] = this.periodEnd.toUtc().toIso8601String();
      json[r'period_start'] = this.periodStart.toUtc().toIso8601String();
      json[r'scope_id'] = this.scopeId;
      json[r'scope_type'] = this.scopeType;
    return json;
  }

  /// Returns a new [AccessUsageRow] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AccessUsageRow? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return AccessUsageRow(
        admitted: mapValueOfType<int>(json, r'admitted')!,
        period: AccessUsageRowPeriodEnum.fromJson(json[r'period'])!,
        periodEnd: mapDateTime(json, r'period_end', r'')!,
        periodStart: mapDateTime(json, r'period_start', r'')!,
        scopeId: mapValueOfType<String>(json, r'scope_id')!,
        scopeType: AccessUsageRowScopeTypeEnum.fromJson(json[r'scope_type'])!,
      );
    }
    return null;
  }

  static List<AccessUsageRow> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AccessUsageRow>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AccessUsageRow.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AccessUsageRow> mapFromJson(dynamic json) {
    final map = <String, AccessUsageRow>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AccessUsageRow.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AccessUsageRow-objects as value to a dart map
  static Map<String, List<AccessUsageRow>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AccessUsageRow>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AccessUsageRow.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'admitted',
    'period',
    'period_end',
    'period_start',
    'scope_id',
    'scope_type',
  };
}


class AccessUsageRowPeriodEnum {
  /// Instantiate a new enum with the provided [value].
  const AccessUsageRowPeriodEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const day = AccessUsageRowPeriodEnum._(r'day');
  static const month = AccessUsageRowPeriodEnum._(r'month');

  /// List of all possible values in this [enum][AccessUsageRowPeriodEnum].
  static const values = <AccessUsageRowPeriodEnum>[
    day,
    month,
  ];

  static AccessUsageRowPeriodEnum? fromJson(dynamic value) => AccessUsageRowPeriodEnumTypeTransformer().decode(value);

  static List<AccessUsageRowPeriodEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AccessUsageRowPeriodEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AccessUsageRowPeriodEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [AccessUsageRowPeriodEnum] to String,
/// and [decode] dynamic data back to [AccessUsageRowPeriodEnum].
class AccessUsageRowPeriodEnumTypeTransformer {
  factory AccessUsageRowPeriodEnumTypeTransformer() => _instance ??= const AccessUsageRowPeriodEnumTypeTransformer._();

  const AccessUsageRowPeriodEnumTypeTransformer._();

  String encode(AccessUsageRowPeriodEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a AccessUsageRowPeriodEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  AccessUsageRowPeriodEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'day': return AccessUsageRowPeriodEnum.day;
        case r'month': return AccessUsageRowPeriodEnum.month;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [AccessUsageRowPeriodEnumTypeTransformer] instance.
  static AccessUsageRowPeriodEnumTypeTransformer? _instance;
}



class AccessUsageRowScopeTypeEnum {
  /// Instantiate a new enum with the provided [value].
  const AccessUsageRowScopeTypeEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const project = AccessUsageRowScopeTypeEnum._(r'project');
  static const slot = AccessUsageRowScopeTypeEnum._(r'slot');
  static const admin = AccessUsageRowScopeTypeEnum._(r'admin');

  /// List of all possible values in this [enum][AccessUsageRowScopeTypeEnum].
  static const values = <AccessUsageRowScopeTypeEnum>[
    project,
    slot,
    admin,
  ];

  static AccessUsageRowScopeTypeEnum? fromJson(dynamic value) => AccessUsageRowScopeTypeEnumTypeTransformer().decode(value);

  static List<AccessUsageRowScopeTypeEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AccessUsageRowScopeTypeEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AccessUsageRowScopeTypeEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [AccessUsageRowScopeTypeEnum] to String,
/// and [decode] dynamic data back to [AccessUsageRowScopeTypeEnum].
class AccessUsageRowScopeTypeEnumTypeTransformer {
  factory AccessUsageRowScopeTypeEnumTypeTransformer() => _instance ??= const AccessUsageRowScopeTypeEnumTypeTransformer._();

  const AccessUsageRowScopeTypeEnumTypeTransformer._();

  String encode(AccessUsageRowScopeTypeEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a AccessUsageRowScopeTypeEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  AccessUsageRowScopeTypeEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'project': return AccessUsageRowScopeTypeEnum.project;
        case r'slot': return AccessUsageRowScopeTypeEnum.slot;
        case r'admin': return AccessUsageRowScopeTypeEnum.admin;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [AccessUsageRowScopeTypeEnumTypeTransformer] instance.
  static AccessUsageRowScopeTypeEnumTypeTransformer? _instance;
}


