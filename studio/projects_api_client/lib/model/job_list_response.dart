//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class JobListResponse {
  /// Returns a new [JobListResponse] instance.
  JobListResponse({
    this.count = 0,
    this.items = const [],
    this.limit = 0,
    this.offset = 0,
  });

  int count;

  List<JobResponse> items;

  int limit;

  int offset;

  @override
  bool operator ==(Object other) => identical(this, other) || other is JobListResponse &&
    other.count == count &&
    _deepEquality.equals(other.items, items) &&
    other.limit == limit &&
    other.offset == offset;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (count.hashCode) +
    (items.hashCode) +
    (limit.hashCode) +
    (offset.hashCode);

  @override
  String toString() => 'JobListResponse[count=$count, items=$items, limit=$limit, offset=$offset]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'count'] = this.count;
      json[r'items'] = this.items;
      json[r'limit'] = this.limit;
      json[r'offset'] = this.offset;
    return json;
  }

  /// Returns a new [JobListResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static JobListResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "JobListResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "JobListResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return JobListResponse(
        count: mapValueOfType<int>(json, r'count') ?? 0,
        items: JobResponse.listFromJson(json[r'items']),
        limit: mapValueOfType<int>(json, r'limit') ?? 0,
        offset: mapValueOfType<int>(json, r'offset') ?? 0,
      );
    }
    return null;
  }

  static List<JobListResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <JobListResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = JobListResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, JobListResponse> mapFromJson(dynamic json) {
    final map = <String, JobListResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = JobListResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of JobListResponse-objects as value to a dart map
  static Map<String, List<JobListResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<JobListResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = JobListResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
  };
}

