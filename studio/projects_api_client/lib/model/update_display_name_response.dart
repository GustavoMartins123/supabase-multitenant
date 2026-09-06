//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class UpdateDisplayNameResponse {
  /// Returns a new [UpdateDisplayNameResponse] instance.
  UpdateDisplayNameResponse({
    required this.displayName,
    required this.project,
    required this.status,
  });

  String displayName;

  String project;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is UpdateDisplayNameResponse &&
    other.displayName == displayName &&
    other.project == project &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName.hashCode) +
    (project.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'UpdateDisplayNameResponse[displayName=$displayName, project=$project, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'display_name'] = this.displayName;
      json[r'project'] = this.project;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [UpdateDisplayNameResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static UpdateDisplayNameResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "UpdateDisplayNameResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "UpdateDisplayNameResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return UpdateDisplayNameResponse(
        displayName: mapValueOfType<String>(json, r'display_name')!,
        project: mapValueOfType<String>(json, r'project')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<UpdateDisplayNameResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <UpdateDisplayNameResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = UpdateDisplayNameResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, UpdateDisplayNameResponse> mapFromJson(dynamic json) {
    final map = <String, UpdateDisplayNameResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = UpdateDisplayNameResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of UpdateDisplayNameResponse-objects as value to a dart map
  static Map<String, List<UpdateDisplayNameResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<UpdateDisplayNameResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = UpdateDisplayNameResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'display_name',
    'project',
    'status',
  };
}

