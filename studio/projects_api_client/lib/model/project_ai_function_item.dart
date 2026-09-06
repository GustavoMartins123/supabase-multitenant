//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectAIFunctionItem {
  /// Returns a new [ProjectAIFunctionItem] instance.
  ProjectAIFunctionItem({
    required this.argumentTypes,
    required this.comment,
    required this.name,
    required this.returnType,
    required this.schema,
  });

  String argumentTypes;

  String comment;

  String name;

  String returnType;

  String schema;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectAIFunctionItem &&
    other.argumentTypes == argumentTypes &&
    other.comment == comment &&
    other.name == name &&
    other.returnType == returnType &&
    other.schema == schema;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (argumentTypes.hashCode) +
    (comment.hashCode) +
    (name.hashCode) +
    (returnType.hashCode) +
    (schema.hashCode);

  @override
  String toString() => 'ProjectAIFunctionItem[argumentTypes=$argumentTypes, comment=$comment, name=$name, returnType=$returnType, schema=$schema]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'argument_types'] = this.argumentTypes;
      json[r'comment'] = this.comment;
      json[r'name'] = this.name;
      json[r'return_type'] = this.returnType;
      json[r'schema'] = this.schema;
    return json;
  }

  /// Returns a new [ProjectAIFunctionItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectAIFunctionItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectAIFunctionItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectAIFunctionItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectAIFunctionItem(
        argumentTypes: mapValueOfType<String>(json, r'argument_types')!,
        comment: mapValueOfType<String>(json, r'comment')!,
        name: mapValueOfType<String>(json, r'name')!,
        returnType: mapValueOfType<String>(json, r'return_type')!,
        schema: mapValueOfType<String>(json, r'schema')!,
      );
    }
    return null;
  }

  static List<ProjectAIFunctionItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectAIFunctionItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectAIFunctionItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectAIFunctionItem> mapFromJson(dynamic json) {
    final map = <String, ProjectAIFunctionItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectAIFunctionItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectAIFunctionItem-objects as value to a dart map
  static Map<String, List<ProjectAIFunctionItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectAIFunctionItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectAIFunctionItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'argument_types',
    'comment',
    'name',
    'return_type',
    'schema',
  };
}

