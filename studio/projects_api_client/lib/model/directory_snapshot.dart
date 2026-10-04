//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class DirectorySnapshot {
  /// Returns a new [DirectorySnapshot] instance.
  DirectorySnapshot({
    required this.revision,
    required this.sequence,
    this.users = const [],
  });

  String revision;

  /// Maximum value: 9007199254740991
  int sequence;

  List<DirectoryUser> users;

  @override
  bool operator ==(Object other) => identical(this, other) || other is DirectorySnapshot &&
    other.revision == revision &&
    other.sequence == sequence &&
    _deepEquality.equals(other.users, users);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (revision.hashCode) +
    (sequence.hashCode) +
    (users.hashCode);

  @override
  String toString() => 'DirectorySnapshot[revision=$revision, sequence=$sequence, users=$users]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'revision'] = this.revision;
      json[r'sequence'] = this.sequence;
      json[r'users'] = this.users;
    return json;
  }

  /// Returns a new [DirectorySnapshot] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static DirectorySnapshot? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return DirectorySnapshot(
        revision: mapValueOfType<String>(json, r'revision')!,
        sequence: mapValueOfType<int>(json, r'sequence')!,
        users: DirectoryUser.listFromJson(json[r'users']),
      );
    }
    return null;
  }

  static List<DirectorySnapshot> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <DirectorySnapshot>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = DirectorySnapshot.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, DirectorySnapshot> mapFromJson(dynamic json) {
    final map = <String, DirectorySnapshot>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = DirectorySnapshot.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of DirectorySnapshot-objects as value to a dart map
  static Map<String, List<DirectorySnapshot>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<DirectorySnapshot>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = DirectorySnapshot.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'revision',
    'sequence',
    'users',
  };
}

