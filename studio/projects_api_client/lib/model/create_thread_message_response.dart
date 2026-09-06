//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CreateThreadMessageResponse {
  /// Returns a new [CreateThreadMessageResponse] instance.
  CreateThreadMessageResponse({
    required this.createdAt,
    required this.id,
    required this.updatedAt,
  });

  String createdAt;

  String id;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CreateThreadMessageResponse &&
    other.createdAt == createdAt &&
    other.id == id &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (createdAt.hashCode) +
    (id.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'CreateThreadMessageResponse[createdAt=$createdAt, id=$id, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [CreateThreadMessageResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CreateThreadMessageResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CreateThreadMessageResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CreateThreadMessageResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CreateThreadMessageResponse(
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<CreateThreadMessageResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CreateThreadMessageResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CreateThreadMessageResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CreateThreadMessageResponse> mapFromJson(dynamic json) {
    final map = <String, CreateThreadMessageResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CreateThreadMessageResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CreateThreadMessageResponse-objects as value to a dart map
  static Map<String, List<CreateThreadMessageResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CreateThreadMessageResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CreateThreadMessageResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'created_at',
    'id',
    'updated_at',
  };
}

