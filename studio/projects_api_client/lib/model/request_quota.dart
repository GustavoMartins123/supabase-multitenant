//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RequestQuota {
  /// Returns a new [RequestQuota] instance.
  RequestQuota({
    required this.limit,
    required this.period,
  });

  /// Minimum value: 1
  /// Maximum value: 1000000000000
  int limit;

  RequestQuotaPeriodEnum period;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RequestQuota &&
    other.limit == limit &&
    other.period == period;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (limit.hashCode) +
    (period.hashCode);

  @override
  String toString() => 'RequestQuota[limit=$limit, period=$period]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'limit'] = this.limit;
      json[r'period'] = this.period;
    return json;
  }

  /// Returns a new [RequestQuota] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RequestQuota? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return RequestQuota(
        limit: mapValueOfType<int>(json, r'limit')!,
        period: RequestQuotaPeriodEnum.fromJson(json[r'period'])!,
      );
    }
    return null;
  }

  static List<RequestQuota> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RequestQuota>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RequestQuota.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RequestQuota> mapFromJson(dynamic json) {
    final map = <String, RequestQuota>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RequestQuota.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RequestQuota-objects as value to a dart map
  static Map<String, List<RequestQuota>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RequestQuota>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RequestQuota.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'limit',
    'period',
  };
}


class RequestQuotaPeriodEnum {
  /// Instantiate a new enum with the provided [value].
  const RequestQuotaPeriodEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const day = RequestQuotaPeriodEnum._(r'day');
  static const month = RequestQuotaPeriodEnum._(r'month');

  /// List of all possible values in this [enum][RequestQuotaPeriodEnum].
  static const values = <RequestQuotaPeriodEnum>[
    day,
    month,
  ];

  static RequestQuotaPeriodEnum? fromJson(dynamic value) => RequestQuotaPeriodEnumTypeTransformer().decode(value);

  static List<RequestQuotaPeriodEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RequestQuotaPeriodEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RequestQuotaPeriodEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [RequestQuotaPeriodEnum] to String,
/// and [decode] dynamic data back to [RequestQuotaPeriodEnum].
class RequestQuotaPeriodEnumTypeTransformer {
  factory RequestQuotaPeriodEnumTypeTransformer() => _instance ??= const RequestQuotaPeriodEnumTypeTransformer._();

  const RequestQuotaPeriodEnumTypeTransformer._();

  String encode(RequestQuotaPeriodEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a RequestQuotaPeriodEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  RequestQuotaPeriodEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'day': return RequestQuotaPeriodEnum.day;
        case r'month': return RequestQuotaPeriodEnum.month;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [RequestQuotaPeriodEnumTypeTransformer] instance.
  static RequestQuotaPeriodEnumTypeTransformer? _instance;
}


