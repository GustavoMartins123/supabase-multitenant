//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SlotListResponse {
  /// Returns a new [SlotListResponse] instance.
  SlotListResponse({
    required this.apiKeysetVersion,
    required this.project,
    this.slots = const [],
  });

  int apiKeysetVersion;

  String project;

  List<SlotItem> slots;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SlotListResponse &&
    other.apiKeysetVersion == apiKeysetVersion &&
    other.project == project &&
    _deepEquality.equals(other.slots, slots);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (apiKeysetVersion.hashCode) +
    (project.hashCode) +
    (slots.hashCode);

  @override
  String toString() => 'SlotListResponse[apiKeysetVersion=$apiKeysetVersion, project=$project, slots=$slots]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'api_keyset_version'] = this.apiKeysetVersion;
      json[r'project'] = this.project;
      json[r'slots'] = this.slots;
    return json;
  }

  /// Returns a new [SlotListResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SlotListResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "SlotListResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "SlotListResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return SlotListResponse(
        apiKeysetVersion: mapValueOfType<int>(json, r'api_keyset_version')!,
        project: mapValueOfType<String>(json, r'project')!,
        slots: SlotItem.listFromJson(json[r'slots']),
      );
    }
    return null;
  }

  static List<SlotListResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SlotListResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SlotListResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SlotListResponse> mapFromJson(dynamic json) {
    final map = <String, SlotListResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SlotListResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SlotListResponse-objects as value to a dart map
  static Map<String, List<SlotListResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SlotListResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SlotListResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'api_keyset_version',
    'project',
    'slots',
  };
}

