//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CollaborationNotificationItem {
  /// Returns a new [CollaborationNotificationItem] instance.
  CollaborationNotificationItem({
    required this.actorName,
    required this.createdAt,
    required this.id,
    required this.kind,
    this.payload = const {},
    required this.readAt,
    required this.targetId,
    required this.targetType,
  });

  String actorName;

  String createdAt;

  String id;

  String kind;

  Map<String, Object> payload;

  String? readAt;

  String? targetId;

  String targetType;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CollaborationNotificationItem &&
    other.actorName == actorName &&
    other.createdAt == createdAt &&
    other.id == id &&
    other.kind == kind &&
    _deepEquality.equals(other.payload, payload) &&
    other.readAt == readAt &&
    other.targetId == targetId &&
    other.targetType == targetType;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (actorName.hashCode) +
    (createdAt.hashCode) +
    (id.hashCode) +
    (kind.hashCode) +
    (payload.hashCode) +
    (readAt == null ? 0 : readAt!.hashCode) +
    (targetId == null ? 0 : targetId!.hashCode) +
    (targetType.hashCode);

  @override
  String toString() => 'CollaborationNotificationItem[actorName=$actorName, createdAt=$createdAt, id=$id, kind=$kind, payload=$payload, readAt=$readAt, targetId=$targetId, targetType=$targetType]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'actor_name'] = this.actorName;
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
      json[r'kind'] = this.kind;
      json[r'payload'] = this.payload;
    if (this.readAt != null) {
      json[r'read_at'] = this.readAt;
    } else {
      json[r'read_at'] = null;
    }
    if (this.targetId != null) {
      json[r'target_id'] = this.targetId;
    } else {
      json[r'target_id'] = null;
    }
      json[r'target_type'] = this.targetType;
    return json;
  }

  /// Returns a new [CollaborationNotificationItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CollaborationNotificationItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CollaborationNotificationItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CollaborationNotificationItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CollaborationNotificationItem(
        actorName: mapValueOfType<String>(json, r'actor_name')!,
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        kind: mapValueOfType<String>(json, r'kind')!,
        payload: mapCastOfType<String, Object>(json, r'payload')!,
        readAt: mapValueOfType<String>(json, r'read_at'),
        targetId: mapValueOfType<String>(json, r'target_id'),
        targetType: mapValueOfType<String>(json, r'target_type')!,
      );
    }
    return null;
  }

  static List<CollaborationNotificationItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CollaborationNotificationItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CollaborationNotificationItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CollaborationNotificationItem> mapFromJson(dynamic json) {
    final map = <String, CollaborationNotificationItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CollaborationNotificationItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CollaborationNotificationItem-objects as value to a dart map
  static Map<String, List<CollaborationNotificationItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CollaborationNotificationItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CollaborationNotificationItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'actor_name',
    'created_at',
    'id',
    'kind',
    'payload',
    'read_at',
    'target_id',
    'target_type',
  };
}

