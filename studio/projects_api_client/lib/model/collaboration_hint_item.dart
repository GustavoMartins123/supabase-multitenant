//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CollaborationHintItem {
  /// Returns a new [CollaborationHintItem] instance.
  CollaborationHintItem({
    required this.authorName,
    required this.authorUserId,
    required this.body,
    required this.canUpdate,
    required this.createdAt,
    required this.id,
    required this.resolvedAt,
    required this.resolvedByName,
    required this.status,
    required this.targetName,
    required this.targetUserId,
    required this.updatedAt,
  });

  String authorName;

  String? authorUserId;

  String body;

  bool canUpdate;

  String createdAt;

  String id;

  String? resolvedAt;

  String? resolvedByName;

  String status;

  String targetName;

  String? targetUserId;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CollaborationHintItem &&
    other.authorName == authorName &&
    other.authorUserId == authorUserId &&
    other.body == body &&
    other.canUpdate == canUpdate &&
    other.createdAt == createdAt &&
    other.id == id &&
    other.resolvedAt == resolvedAt &&
    other.resolvedByName == resolvedByName &&
    other.status == status &&
    other.targetName == targetName &&
    other.targetUserId == targetUserId &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (authorName.hashCode) +
    (authorUserId == null ? 0 : authorUserId!.hashCode) +
    (body.hashCode) +
    (canUpdate.hashCode) +
    (createdAt.hashCode) +
    (id.hashCode) +
    (resolvedAt == null ? 0 : resolvedAt!.hashCode) +
    (resolvedByName == null ? 0 : resolvedByName!.hashCode) +
    (status.hashCode) +
    (targetName.hashCode) +
    (targetUserId == null ? 0 : targetUserId!.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'CollaborationHintItem[authorName=$authorName, authorUserId=$authorUserId, body=$body, canUpdate=$canUpdate, createdAt=$createdAt, id=$id, resolvedAt=$resolvedAt, resolvedByName=$resolvedByName, status=$status, targetName=$targetName, targetUserId=$targetUserId, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'author_name'] = this.authorName;
    if (this.authorUserId != null) {
      json[r'author_user_id'] = this.authorUserId;
    } else {
      json[r'author_user_id'] = null;
    }
      json[r'body'] = this.body;
      json[r'can_update'] = this.canUpdate;
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
    if (this.resolvedAt != null) {
      json[r'resolved_at'] = this.resolvedAt;
    } else {
      json[r'resolved_at'] = null;
    }
    if (this.resolvedByName != null) {
      json[r'resolved_by_name'] = this.resolvedByName;
    } else {
      json[r'resolved_by_name'] = null;
    }
      json[r'status'] = this.status;
      json[r'target_name'] = this.targetName;
    if (this.targetUserId != null) {
      json[r'target_user_id'] = this.targetUserId;
    } else {
      json[r'target_user_id'] = null;
    }
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [CollaborationHintItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CollaborationHintItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CollaborationHintItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CollaborationHintItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CollaborationHintItem(
        authorName: mapValueOfType<String>(json, r'author_name')!,
        authorUserId: mapValueOfType<String>(json, r'author_user_id'),
        body: mapValueOfType<String>(json, r'body')!,
        canUpdate: mapValueOfType<bool>(json, r'can_update')!,
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        resolvedAt: mapValueOfType<String>(json, r'resolved_at'),
        resolvedByName: mapValueOfType<String>(json, r'resolved_by_name'),
        status: mapValueOfType<String>(json, r'status')!,
        targetName: mapValueOfType<String>(json, r'target_name')!,
        targetUserId: mapValueOfType<String>(json, r'target_user_id'),
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<CollaborationHintItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CollaborationHintItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CollaborationHintItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CollaborationHintItem> mapFromJson(dynamic json) {
    final map = <String, CollaborationHintItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CollaborationHintItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CollaborationHintItem-objects as value to a dart map
  static Map<String, List<CollaborationHintItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CollaborationHintItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CollaborationHintItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'author_name',
    'author_user_id',
    'body',
    'can_update',
    'created_at',
    'id',
    'resolved_at',
    'resolved_by_name',
    'status',
    'target_name',
    'target_user_id',
    'updated_at',
  };
}

