//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AllUsersResponse {
  /// Returns a new [AllUsersResponse] instance.
  AllUsersResponse({
    required this.cacheUsersNeeded,
    this.currentMembers = const [],
    required this.nginxRoute,
    required this.projectId,
    required this.projectName,
  });

  bool cacheUsersNeeded;

  List<AllUsersMemberItem> currentMembers;

  String nginxRoute;

  String projectId;

  String projectName;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AllUsersResponse &&
    other.cacheUsersNeeded == cacheUsersNeeded &&
    _deepEquality.equals(other.currentMembers, currentMembers) &&
    other.nginxRoute == nginxRoute &&
    other.projectId == projectId &&
    other.projectName == projectName;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (cacheUsersNeeded.hashCode) +
    (currentMembers.hashCode) +
    (nginxRoute.hashCode) +
    (projectId.hashCode) +
    (projectName.hashCode);

  @override
  String toString() => 'AllUsersResponse[cacheUsersNeeded=$cacheUsersNeeded, currentMembers=$currentMembers, nginxRoute=$nginxRoute, projectId=$projectId, projectName=$projectName]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'cache_users_needed'] = this.cacheUsersNeeded;
      json[r'current_members'] = this.currentMembers;
      json[r'nginx_route'] = this.nginxRoute;
      json[r'project_id'] = this.projectId;
      json[r'project_name'] = this.projectName;
    return json;
  }

  /// Returns a new [AllUsersResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AllUsersResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "AllUsersResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "AllUsersResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return AllUsersResponse(
        cacheUsersNeeded: mapValueOfType<bool>(json, r'cache_users_needed')!,
        currentMembers: AllUsersMemberItem.listFromJson(json[r'current_members']),
        nginxRoute: mapValueOfType<String>(json, r'nginx_route')!,
        projectId: mapValueOfType<String>(json, r'project_id')!,
        projectName: mapValueOfType<String>(json, r'project_name')!,
      );
    }
    return null;
  }

  static List<AllUsersResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AllUsersResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AllUsersResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AllUsersResponse> mapFromJson(dynamic json) {
    final map = <String, AllUsersResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AllUsersResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AllUsersResponse-objects as value to a dart map
  static Map<String, List<AllUsersResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AllUsersResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AllUsersResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'cache_users_needed',
    'current_members',
    'nginx_route',
    'project_id',
    'project_name',
  };
}

