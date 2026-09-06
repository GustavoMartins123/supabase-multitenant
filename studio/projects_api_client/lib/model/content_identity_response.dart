//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ContentIdentityResponse {
  /// Returns a new [ContentIdentityResponse] instance.
  ContentIdentityResponse({
    this.aliases = const [],
    required this.currentRef,
    required this.projectId,
  });

  List<String> aliases;

  String currentRef;

  String projectId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ContentIdentityResponse &&
    _deepEquality.equals(other.aliases, aliases) &&
    other.currentRef == currentRef &&
    other.projectId == projectId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (aliases.hashCode) +
    (currentRef.hashCode) +
    (projectId.hashCode);

  @override
  String toString() => 'ContentIdentityResponse[aliases=$aliases, currentRef=$currentRef, projectId=$projectId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'aliases'] = this.aliases;
      json[r'current_ref'] = this.currentRef;
      json[r'project_id'] = this.projectId;
    return json;
  }

  /// Returns a new [ContentIdentityResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ContentIdentityResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ContentIdentityResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ContentIdentityResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ContentIdentityResponse(
        aliases: json[r'aliases'] is Iterable
            ? (json[r'aliases'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        currentRef: mapValueOfType<String>(json, r'current_ref')!,
        projectId: mapValueOfType<String>(json, r'project_id')!,
      );
    }
    return null;
  }

  static List<ContentIdentityResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ContentIdentityResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ContentIdentityResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ContentIdentityResponse> mapFromJson(dynamic json) {
    final map = <String, ContentIdentityResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ContentIdentityResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ContentIdentityResponse-objects as value to a dart map
  static Map<String, List<ContentIdentityResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ContentIdentityResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ContentIdentityResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'aliases',
    'current_ref',
    'project_id',
  };
}

