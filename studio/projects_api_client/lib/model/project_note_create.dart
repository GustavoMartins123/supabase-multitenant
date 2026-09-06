//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectNoteCreate {
  /// Returns a new [ProjectNoteCreate] instance.
  ProjectNoteCreate({
    required this.body,
    this.visibility = 'private',
  });

  String body;

  String visibility;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectNoteCreate &&
    other.body == body &&
    other.visibility == visibility;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (body.hashCode) +
    (visibility.hashCode);

  @override
  String toString() => 'ProjectNoteCreate[body=$body, visibility=$visibility]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'body'] = this.body;
      json[r'visibility'] = this.visibility;
    return json;
  }

  /// Returns a new [ProjectNoteCreate] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectNoteCreate? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectNoteCreate[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectNoteCreate[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectNoteCreate(
        body: mapValueOfType<String>(json, r'body')!,
        visibility: mapValueOfType<String>(json, r'visibility') ?? 'private',
      );
    }
    return null;
  }

  static List<ProjectNoteCreate> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectNoteCreate>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectNoteCreate.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectNoteCreate> mapFromJson(dynamic json) {
    final map = <String, ProjectNoteCreate>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectNoteCreate.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectNoteCreate-objects as value to a dart map
  static Map<String, List<ProjectNoteCreate>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectNoteCreate>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectNoteCreate.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'body',
  };
}

