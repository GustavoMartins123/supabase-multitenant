//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ListRestorePointsResponse {
  /// Returns a new [ListRestorePointsResponse] instance.
  ListRestorePointsResponse({
    required this.limit,
    required this.permissions,
    this.points = const [],
    required this.project,
  });

  int limit;

  RestorePointsPermissions permissions;

  List<RestorePointItem> points;

  String project;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ListRestorePointsResponse &&
    other.limit == limit &&
    other.permissions == permissions &&
    _deepEquality.equals(other.points, points) &&
    other.project == project;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (limit.hashCode) +
    (permissions.hashCode) +
    (points.hashCode) +
    (project.hashCode);

  @override
  String toString() => 'ListRestorePointsResponse[limit=$limit, permissions=$permissions, points=$points, project=$project]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'limit'] = this.limit;
      json[r'permissions'] = this.permissions;
      json[r'points'] = this.points;
      json[r'project'] = this.project;
    return json;
  }

  /// Returns a new [ListRestorePointsResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ListRestorePointsResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ListRestorePointsResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ListRestorePointsResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ListRestorePointsResponse(
        limit: mapValueOfType<int>(json, r'limit')!,
        permissions: RestorePointsPermissions.fromJson(json[r'permissions'])!,
        points: RestorePointItem.listFromJson(json[r'points']),
        project: mapValueOfType<String>(json, r'project')!,
      );
    }
    return null;
  }

  static List<ListRestorePointsResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ListRestorePointsResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ListRestorePointsResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ListRestorePointsResponse> mapFromJson(dynamic json) {
    final map = <String, ListRestorePointsResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ListRestorePointsResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ListRestorePointsResponse-objects as value to a dart map
  static Map<String, List<ListRestorePointsResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ListRestorePointsResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ListRestorePointsResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'limit',
    'permissions',
    'points',
    'project',
  };
}

