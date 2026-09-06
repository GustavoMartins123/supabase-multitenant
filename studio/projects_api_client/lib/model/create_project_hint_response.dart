//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CreateProjectHintResponse {
  /// Returns a new [CreateProjectHintResponse] instance.
  CreateProjectHintResponse({
    required this.createdAt,
    required this.id,
    required this.status,
    required this.updatedAt,
  });

  String createdAt;

  String id;

  String status;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CreateProjectHintResponse &&
    other.createdAt == createdAt &&
    other.id == id &&
    other.status == status &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (createdAt.hashCode) +
    (id.hashCode) +
    (status.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'CreateProjectHintResponse[createdAt=$createdAt, id=$id, status=$status, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
      json[r'status'] = this.status;
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [CreateProjectHintResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CreateProjectHintResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CreateProjectHintResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CreateProjectHintResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CreateProjectHintResponse(
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        status: mapValueOfType<String>(json, r'status')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<CreateProjectHintResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CreateProjectHintResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CreateProjectHintResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CreateProjectHintResponse> mapFromJson(dynamic json) {
    final map = <String, CreateProjectHintResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CreateProjectHintResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CreateProjectHintResponse-objects as value to a dart map
  static Map<String, List<CreateProjectHintResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CreateProjectHintResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CreateProjectHintResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'created_at',
    'id',
    'status',
    'updated_at',
  };
}

