//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AccessPolicy {
  /// Returns a new [AccessPolicy] instance.
  AccessPolicy({
    this.allowedCountries = const [],
    this.allowedNetworks = const [],
    required this.geoMode,
    required this.rateLimit,
    required this.requestQuota,
  });

  List<String>? allowedCountries;

  List<String> allowedNetworks;

  AccessPolicyGeoModeEnum geoMode;

  RateLimit rateLimit;

  RequestQuota requestQuota;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AccessPolicy &&
    _deepEquality.equals(other.allowedCountries, allowedCountries) &&
    _deepEquality.equals(other.allowedNetworks, allowedNetworks) &&
    other.geoMode == geoMode &&
    other.rateLimit == rateLimit &&
    other.requestQuota == requestQuota;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (allowedCountries == null ? 0 : allowedCountries!.hashCode) +
    (allowedNetworks.hashCode) +
    (geoMode.hashCode) +
    (rateLimit.hashCode) +
    (requestQuota.hashCode);

  @override
  String toString() => 'AccessPolicy[allowedCountries=$allowedCountries, allowedNetworks=$allowedNetworks, geoMode=$geoMode, rateLimit=$rateLimit, requestQuota=$requestQuota]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.allowedCountries != null) {
      json[r'allowed_countries'] = this.allowedCountries;
    } else {
      json[r'allowed_countries'] = null;
    }
      json[r'allowed_networks'] = this.allowedNetworks;
      json[r'geo_mode'] = this.geoMode;
      json[r'rate_limit'] = this.rateLimit;
      json[r'request_quota'] = this.requestQuota;
    return json;
  }

  /// Returns a new [AccessPolicy] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AccessPolicy? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'allowed_countries', r'rate_limit', r'request_quota'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return AccessPolicy(
        allowedCountries: json[r'allowed_countries'] is Iterable
            ? (json[r'allowed_countries'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        allowedNetworks: json[r'allowed_networks'] is Iterable
            ? (json[r'allowed_networks'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        geoMode: AccessPolicyGeoModeEnum.fromJson(json[r'geo_mode'])!,
        rateLimit: RateLimit.fromJson(json[r'rate_limit'])!,
        requestQuota: RequestQuota.fromJson(json[r'request_quota'])!,
      );
    }
    return null;
  }

  static List<AccessPolicy> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AccessPolicy>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AccessPolicy.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AccessPolicy> mapFromJson(dynamic json) {
    final map = <String, AccessPolicy>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AccessPolicy.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AccessPolicy-objects as value to a dart map
  static Map<String, List<AccessPolicy>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AccessPolicy>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AccessPolicy.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'allowed_countries',
    'allowed_networks',
    'geo_mode',
    'rate_limit',
    'request_quota',
  };
}


class AccessPolicyGeoModeEnum {
  /// Instantiate a new enum with the provided [value].
  const AccessPolicyGeoModeEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const unrestricted = AccessPolicyGeoModeEnum._(r'unrestricted');
  static const inherit = AccessPolicyGeoModeEnum._(r'inherit');
  static const restrict = AccessPolicyGeoModeEnum._(r'restrict');

  /// List of all possible values in this [enum][AccessPolicyGeoModeEnum].
  static const values = <AccessPolicyGeoModeEnum>[
    unrestricted,
    inherit,
    restrict,
  ];

  static AccessPolicyGeoModeEnum? fromJson(dynamic value) => AccessPolicyGeoModeEnumTypeTransformer().decode(value);

  static List<AccessPolicyGeoModeEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AccessPolicyGeoModeEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AccessPolicyGeoModeEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [AccessPolicyGeoModeEnum] to String,
/// and [decode] dynamic data back to [AccessPolicyGeoModeEnum].
class AccessPolicyGeoModeEnumTypeTransformer {
  factory AccessPolicyGeoModeEnumTypeTransformer() => _instance ??= const AccessPolicyGeoModeEnumTypeTransformer._();

  const AccessPolicyGeoModeEnumTypeTransformer._();

  String encode(AccessPolicyGeoModeEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a AccessPolicyGeoModeEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  AccessPolicyGeoModeEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'unrestricted': return AccessPolicyGeoModeEnum.unrestricted;
        case r'inherit': return AccessPolicyGeoModeEnum.inherit;
        case r'restrict': return AccessPolicyGeoModeEnum.restrict;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [AccessPolicyGeoModeEnumTypeTransformer] instance.
  static AccessPolicyGeoModeEnumTypeTransformer? _instance;
}


