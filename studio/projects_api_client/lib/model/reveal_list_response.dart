//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RevealListResponse {
  /// Returns a new [RevealListResponse] instance.
  RevealListResponse({
    required this.project,
    this.reveals = const [],
  });

  String project;

  List<RevealItem> reveals;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RevealListResponse &&
    other.project == project &&
    _deepEquality.equals(other.reveals, reveals);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (project.hashCode) +
    (reveals.hashCode);

  @override
  String toString() => 'RevealListResponse[project=$project, reveals=$reveals]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'project'] = this.project;
      json[r'reveals'] = this.reveals;
    return json;
  }

  /// Returns a new [RevealListResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RevealListResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RevealListResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RevealListResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RevealListResponse(
        project: mapValueOfType<String>(json, r'project')!,
        reveals: RevealItem.listFromJson(json[r'reveals']),
      );
    }
    return null;
  }

  static List<RevealListResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RevealListResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RevealListResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RevealListResponse> mapFromJson(dynamic json) {
    final map = <String, RevealListResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RevealListResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RevealListResponse-objects as value to a dart map
  static Map<String, List<RevealListResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RevealListResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RevealListResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'project',
    'reveals',
  };
}

