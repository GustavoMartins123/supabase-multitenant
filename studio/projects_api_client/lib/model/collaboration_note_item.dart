//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CollaborationNoteItem {
  /// Returns a new [CollaborationNoteItem] instance.
  CollaborationNoteItem({
    required this.authorName,
    required this.authorUserId,
    required this.body,
    required this.createdAt,
    required this.id,
    required this.isEncrypted,
    required this.updatedAt,
    required this.visibility,
  });

  String authorName;

  String? authorUserId;

  String body;

  String createdAt;

  String id;

  bool isEncrypted;

  String updatedAt;

  String visibility;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CollaborationNoteItem &&
    other.authorName == authorName &&
    other.authorUserId == authorUserId &&
    other.body == body &&
    other.createdAt == createdAt &&
    other.id == id &&
    other.isEncrypted == isEncrypted &&
    other.updatedAt == updatedAt &&
    other.visibility == visibility;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (authorName.hashCode) +
    (authorUserId == null ? 0 : authorUserId!.hashCode) +
    (body.hashCode) +
    (createdAt.hashCode) +
    (id.hashCode) +
    (isEncrypted.hashCode) +
    (updatedAt.hashCode) +
    (visibility.hashCode);

  @override
  String toString() => 'CollaborationNoteItem[authorName=$authorName, authorUserId=$authorUserId, body=$body, createdAt=$createdAt, id=$id, isEncrypted=$isEncrypted, updatedAt=$updatedAt, visibility=$visibility]';

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
      json[r'is_encrypted'] = this.isEncrypted;
      json[r'updated_at'] = this.updatedAt;
      json[r'visibility'] = this.visibility;
    return json;
  }

  /// Returns a new [CollaborationNoteItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CollaborationNoteItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CollaborationNoteItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CollaborationNoteItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CollaborationNoteItem(
        authorName: mapValueOfType<String>(json, r'author_name')!,
        authorUserId: mapValueOfType<String>(json, r'author_user_id'),
        body: mapValueOfType<String>(json, r'body')!,
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        isEncrypted: mapValueOfType<bool>(json, r'is_encrypted')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
        visibility: mapValueOfType<String>(json, r'visibility')!,
      );
    }
    return null;
  }

  static List<CollaborationNoteItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CollaborationNoteItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CollaborationNoteItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CollaborationNoteItem> mapFromJson(dynamic json) {
    final map = <String, CollaborationNoteItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CollaborationNoteItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CollaborationNoteItem-objects as value to a dart map
  static Map<String, List<CollaborationNoteItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CollaborationNoteItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CollaborationNoteItem.listFromJson(entry.value, growable: growable,);
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
    'is_encrypted',
    'updated_at',
    'visibility',
  };
}

