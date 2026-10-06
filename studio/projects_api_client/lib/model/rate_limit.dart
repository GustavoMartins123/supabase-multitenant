//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RateLimit {
  /// Returns a new [RateLimit] instance.
  RateLimit({
    required this.burst,
    required this.requestsPerSecond,
  });

  /// Minimum value: 1
  /// Maximum value: 1000000
  int burst;

  /// Minimum value: 1
  /// Maximum value: 100000
  int requestsPerSecond;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RateLimit &&
    other.burst == burst &&
    other.requestsPerSecond == requestsPerSecond;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (burst.hashCode) +
    (requestsPerSecond.hashCode);

  @override
  String toString() => 'RateLimit[burst=$burst, requestsPerSecond=$requestsPerSecond]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'burst'] = this.burst;
      json[r'requests_per_second'] = this.requestsPerSecond;
    return json;
  }

  /// Returns a new [RateLimit] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RateLimit? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return RateLimit(
        burst: mapValueOfType<int>(json, r'burst')!,
        requestsPerSecond: mapValueOfType<int>(json, r'requests_per_second')!,
      );
    }
    return null;
  }

  static List<RateLimit> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RateLimit>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RateLimit.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RateLimit> mapFromJson(dynamic json) {
    final map = <String, RateLimit>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RateLimit.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RateLimit-objects as value to a dart map
  static Map<String, List<RateLimit>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RateLimit>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RateLimit.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'burst',
    'requests_per_second',
  };
}

