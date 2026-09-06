//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AssignProjectTagResponse {
  /// Returns a new [AssignProjectTagResponse] instance.
  AssignProjectTagResponse({
    required this.assigned,
    required this.category,
    required this.color,
    required this.id,
    required this.isSystem,
    required this.name,
  });

  bool assigned;

  String category;

  String color;

  String id;

  bool isSystem;

  String name;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AssignProjectTagResponse &&
    other.assigned == assigned &&
    other.category == category &&
    other.color == color &&
    other.id == id &&
    other.isSystem == isSystem &&
    other.name == name;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (assigned.hashCode) +
    (category.hashCode) +
    (color.hashCode) +
    (id.hashCode) +
    (isSystem.hashCode) +
    (name.hashCode);

  @override
  String toString() => 'AssignProjectTagResponse[assigned=$assigned, category=$category, color=$color, id=$id, isSystem=$isSystem, name=$name]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'assigned'] = this.assigned;
      json[r'category'] = this.category;
      json[r'color'] = this.color;
      json[r'id'] = this.id;
      json[r'is_system'] = this.isSystem;
      json[r'name'] = this.name;
    return json;
  }

  /// Returns a new [AssignProjectTagResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AssignProjectTagResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "AssignProjectTagResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "AssignProjectTagResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return AssignProjectTagResponse(
        assigned: mapValueOfType<bool>(json, r'assigned')!,
        category: mapValueOfType<String>(json, r'category')!,
        color: mapValueOfType<String>(json, r'color')!,
        id: mapValueOfType<String>(json, r'id')!,
        isSystem: mapValueOfType<bool>(json, r'is_system')!,
        name: mapValueOfType<String>(json, r'name')!,
      );
    }
    return null;
  }

  static List<AssignProjectTagResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AssignProjectTagResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AssignProjectTagResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AssignProjectTagResponse> mapFromJson(dynamic json) {
    final map = <String, AssignProjectTagResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AssignProjectTagResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AssignProjectTagResponse-objects as value to a dart map
  static Map<String, List<AssignProjectTagResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AssignProjectTagResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AssignProjectTagResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'assigned',
    'category',
    'color',
    'id',
    'is_system',
    'name',
  };
}

