//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class DirectoryUser {
  /// Returns a new [DirectoryUser] instance.
  DirectoryUser({
    required this.displayName,
    this.groups = const [],
    required this.id,
    required this.isActive,
    this.source_ = const {},
    required this.username,
  });

  String? displayName;

  List<String> groups;

  String id;

  bool isActive;

  Map<String, Object> source_;

  String username;

  @override
  bool operator ==(Object other) => identical(this, other) || other is DirectoryUser &&
    other.displayName == displayName &&
    _deepEquality.equals(other.groups, groups) &&
    other.id == id &&
    other.isActive == isActive &&
    _deepEquality.equals(other.source_, source_) &&
    other.username == username;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (displayName == null ? 0 : displayName!.hashCode) +
    (groups.hashCode) +
    (id.hashCode) +
    (isActive.hashCode) +
    (source_.hashCode) +
    (username.hashCode);

  @override
  String toString() => 'DirectoryUser[displayName=$displayName, groups=$groups, id=$id, isActive=$isActive, source_=$source_, username=$username]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.displayName != null) {
      json[r'display_name'] = this.displayName;
    } else {
      json[r'display_name'] = null;
    }
      json[r'groups'] = this.groups;
      json[r'id'] = this.id;
      json[r'is_active'] = this.isActive;
      json[r'source'] = this.source_;
      json[r'username'] = this.username;
    return json;
  }

  /// Returns a new [DirectoryUser] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static DirectoryUser? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "DirectoryUser[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "DirectoryUser[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return DirectoryUser(
        displayName: mapValueOfType<String>(json, r'display_name'),
        groups: json[r'groups'] is Iterable
            ? (json[r'groups'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        id: mapValueOfType<String>(json, r'id')!,
        isActive: mapValueOfType<bool>(json, r'is_active')!,
        source_: mapCastOfType<String, Object>(json, r'source')!,
        username: mapValueOfType<String>(json, r'username')!,
      );
    }
    return null;
  }

  static List<DirectoryUser> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <DirectoryUser>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = DirectoryUser.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, DirectoryUser> mapFromJson(dynamic json) {
    final map = <String, DirectoryUser>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = DirectoryUser.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of DirectoryUser-objects as value to a dart map
  static Map<String, List<DirectoryUser>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<DirectoryUser>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = DirectoryUser.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'display_name',
    'groups',
    'id',
    'is_active',
    'source',
    'username',
  };
}

