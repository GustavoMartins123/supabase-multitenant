//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CollaborationThreadItem {
  /// Returns a new [CollaborationThreadItem] instance.
  CollaborationThreadItem({
    required this.authorName,
    required this.authorUserId,
    required this.body,
    required this.createdAt,
    required this.id,
    required this.updatedAt,
  });

  String authorName;

  String? authorUserId;

  String body;

  String createdAt;

  String id;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CollaborationThreadItem &&
    other.authorName == authorName &&
    other.authorUserId == authorUserId &&
    other.body == body &&
    other.createdAt == createdAt &&
    other.id == id &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (authorName.hashCode) +
    (authorUserId == null ? 0 : authorUserId!.hashCode) +
    (body.hashCode) +
    (createdAt.hashCode) +
    (id.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'CollaborationThreadItem[authorName=$authorName, authorUserId=$authorUserId, body=$body, createdAt=$createdAt, id=$id, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'author_name'] = this.authorName;
    if (this.authorUserId != null) {
      json[r'author_user_id'] = this.authorUserId;
    } else {
      json[r'author_user_id'] = null;
    }
      json[r'body'] = this.body;
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [CollaborationThreadItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CollaborationThreadItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CollaborationThreadItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CollaborationThreadItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CollaborationThreadItem(
        authorName: mapValueOfType<String>(json, r'author_name')!,
        authorUserId: mapValueOfType<String>(json, r'author_user_id'),
        body: mapValueOfType<String>(json, r'body')!,
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<CollaborationThreadItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CollaborationThreadItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CollaborationThreadItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CollaborationThreadItem> mapFromJson(dynamic json) {
    final map = <String, CollaborationThreadItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CollaborationThreadItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CollaborationThreadItem-objects as value to a dart map
  static Map<String, List<CollaborationThreadItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CollaborationThreadItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CollaborationThreadItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'author_name',
    'author_user_id',
    'body',
    'created_at',
    'id',
    'updated_at',
  };
}

