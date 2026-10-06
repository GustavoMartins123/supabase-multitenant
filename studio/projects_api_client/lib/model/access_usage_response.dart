//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AccessUsageResponse {
  /// Returns a new [AccessUsageResponse] instance.
  AccessUsageResponse({
    this.usage = const [],
  });

  List<AccessUsageRow> usage;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AccessUsageResponse &&
    _deepEquality.equals(other.usage, usage);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (usage.hashCode);

  @override
  String toString() => 'AccessUsageResponse[usage=$usage]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'usage'] = this.usage;
    return json;
  }

  /// Returns a new [AccessUsageResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AccessUsageResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return AccessUsageResponse(
        usage: AccessUsageRow.listFromJson(json[r'usage']),
      );
    }
    return null;
  }

  static List<AccessUsageResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AccessUsageResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AccessUsageResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AccessUsageResponse> mapFromJson(dynamic json) {
    final map = <String, AccessUsageResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AccessUsageResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AccessUsageResponse-objects as value to a dart map
  static Map<String, List<AccessUsageResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AccessUsageResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AccessUsageResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'usage',
  };
}

