//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class MigrationPrepareResponse {
  /// Returns a new [MigrationPrepareResponse] instance.
  MigrationPrepareResponse({
    this.keyIds = const [],
    required this.next,
    required this.project,
    required this.status,
  });

  List<String> keyIds;

  String next;

  String project;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is MigrationPrepareResponse &&
    _deepEquality.equals(other.keyIds, keyIds) &&
    other.next == next &&
    other.project == project &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (keyIds.hashCode) +
    (next.hashCode) +
    (project.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'MigrationPrepareResponse[keyIds=$keyIds, next=$next, project=$project, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'key_ids'] = this.keyIds;
      json[r'next'] = this.next;
      json[r'project'] = this.project;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [MigrationPrepareResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static MigrationPrepareResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "MigrationPrepareResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "MigrationPrepareResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return MigrationPrepareResponse(
        keyIds: json[r'key_ids'] is Iterable
            ? (json[r'key_ids'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        next: mapValueOfType<String>(json, r'next')!,
        project: mapValueOfType<String>(json, r'project')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<MigrationPrepareResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <MigrationPrepareResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = MigrationPrepareResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, MigrationPrepareResponse> mapFromJson(dynamic json) {
    final map = <String, MigrationPrepareResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = MigrationPrepareResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of MigrationPrepareResponse-objects as value to a dart map
  static Map<String, List<MigrationPrepareResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<MigrationPrepareResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = MigrationPrepareResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'key_ids',
    'next',
    'project',
    'status',
  };
}

