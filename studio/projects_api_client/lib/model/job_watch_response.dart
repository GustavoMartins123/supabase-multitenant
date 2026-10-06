//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class JobWatchResponse {
  /// Returns a new [JobWatchResponse] instance.
  JobWatchResponse({
    required this.cursor,
    this.items = const [],
  });

  String cursor;

  List<JobResponse> items;

  @override
  bool operator ==(Object other) => identical(this, other) || other is JobWatchResponse &&
    other.cursor == cursor &&
    _deepEquality.equals(other.items, items);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (cursor.hashCode) +
    (items.hashCode);

  @override
  String toString() => 'JobWatchResponse[cursor=$cursor, items=$items]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'cursor'] = this.cursor;
      json[r'items'] = this.items;
    return json;
  }

  /// Returns a new [JobWatchResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static JobWatchResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return JobWatchResponse(
        cursor: mapValueOfType<String>(json, r'cursor')!,
        items: JobResponse.listFromJson(json[r'items']),
      );
    }
    return null;
  }

  static List<JobWatchResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <JobWatchResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = JobWatchResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, JobWatchResponse> mapFromJson(dynamic json) {
    final map = <String, JobWatchResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = JobWatchResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of JobWatchResponse-objects as value to a dart map
  static Map<String, List<JobWatchResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<JobWatchResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = JobWatchResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'cursor',
    'items',
  };
}

