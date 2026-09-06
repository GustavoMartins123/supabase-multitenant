//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectRenameHistoryResponse {
  /// Returns a new [ProjectRenameHistoryResponse] instance.
  ProjectRenameHistoryResponse({
    this.events = const [],
    required this.project,
    this.renames = const [],
    required this.requestedName,
  });

  List<RenameHistoryEvent> events;

  String project;

  List<RenameHistoryEntry> renames;

  String requestedName;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectRenameHistoryResponse &&
    _deepEquality.equals(other.events, events) &&
    other.project == project &&
    _deepEquality.equals(other.renames, renames) &&
    other.requestedName == requestedName;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (events.hashCode) +
    (project.hashCode) +
    (renames.hashCode) +
    (requestedName.hashCode);

  @override
  String toString() => 'ProjectRenameHistoryResponse[events=$events, project=$project, renames=$renames, requestedName=$requestedName]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'events'] = this.events;
      json[r'project'] = this.project;
      json[r'renames'] = this.renames;
      json[r'requested_name'] = this.requestedName;
    return json;
  }

  /// Returns a new [ProjectRenameHistoryResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectRenameHistoryResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectRenameHistoryResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectRenameHistoryResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectRenameHistoryResponse(
        events: RenameHistoryEvent.listFromJson(json[r'events']),
        project: mapValueOfType<String>(json, r'project')!,
        renames: RenameHistoryEntry.listFromJson(json[r'renames']),
        requestedName: mapValueOfType<String>(json, r'requested_name')!,
      );
    }
    return null;
  }

  static List<ProjectRenameHistoryResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectRenameHistoryResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectRenameHistoryResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectRenameHistoryResponse> mapFromJson(dynamic json) {
    final map = <String, ProjectRenameHistoryResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectRenameHistoryResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectRenameHistoryResponse-objects as value to a dart map
  static Map<String, List<ProjectRenameHistoryResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectRenameHistoryResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectRenameHistoryResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'events',
    'project',
    'renames',
    'requested_name',
  };
}

