//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RenameHistoryEvent {
  /// Returns a new [RenameHistoryEvent] instance.
  RenameHistoryEvent({
    required this.action,
    required this.actorName,
    required this.actorUserId,
    required this.createdAt,
    required this.id,
    this.newValue = const {},
    this.oldValue = const {},
    required this.targetId,
  });

  String action;

  String actorName;

  String? actorUserId;

  String createdAt;

  int id;

  Map<String, Object>? newValue;

  Map<String, Object>? oldValue;

  String? targetId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RenameHistoryEvent &&
    other.action == action &&
    other.actorName == actorName &&
    other.actorUserId == actorUserId &&
    other.createdAt == createdAt &&
    other.id == id &&
    _deepEquality.equals(other.newValue, newValue) &&
    _deepEquality.equals(other.oldValue, oldValue) &&
    other.targetId == targetId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (action.hashCode) +
    (actorName.hashCode) +
    (actorUserId == null ? 0 : actorUserId!.hashCode) +
    (createdAt.hashCode) +
    (id.hashCode) +
    (newValue == null ? 0 : newValue!.hashCode) +
    (oldValue == null ? 0 : oldValue!.hashCode) +
    (targetId == null ? 0 : targetId!.hashCode);

  @override
  String toString() => 'RenameHistoryEvent[action=$action, actorName=$actorName, actorUserId=$actorUserId, createdAt=$createdAt, id=$id, newValue=$newValue, oldValue=$oldValue, targetId=$targetId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'action'] = this.action;
      json[r'actor_name'] = this.actorName;
    if (this.actorUserId != null) {
      json[r'actor_user_id'] = this.actorUserId;
    } else {
      json[r'actor_user_id'] = null;
    }
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
    if (this.newValue != null) {
      json[r'new_value'] = this.newValue;
    } else {
      json[r'new_value'] = null;
    }
    if (this.oldValue != null) {
      json[r'old_value'] = this.oldValue;
    } else {
      json[r'old_value'] = null;
    }
    if (this.targetId != null) {
      json[r'target_id'] = this.targetId;
    } else {
      json[r'target_id'] = null;
    }
    return json;
  }

  /// Returns a new [RenameHistoryEvent] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RenameHistoryEvent? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RenameHistoryEvent[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RenameHistoryEvent[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RenameHistoryEvent(
        action: mapValueOfType<String>(json, r'action')!,
        actorName: mapValueOfType<String>(json, r'actor_name')!,
        actorUserId: mapValueOfType<String>(json, r'actor_user_id'),
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<int>(json, r'id')!,
        newValue: mapCastOfType<String, Object>(json, r'new_value'),
        oldValue: mapCastOfType<String, Object>(json, r'old_value'),
        targetId: mapValueOfType<String>(json, r'target_id'),
      );
    }
    return null;
  }

  static List<RenameHistoryEvent> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RenameHistoryEvent>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RenameHistoryEvent.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RenameHistoryEvent> mapFromJson(dynamic json) {
    final map = <String, RenameHistoryEvent>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RenameHistoryEvent.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RenameHistoryEvent-objects as value to a dart map
  static Map<String, List<RenameHistoryEvent>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RenameHistoryEvent>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RenameHistoryEvent.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'action',
    'actor_name',
    'actor_user_id',
    'created_at',
    'id',
    'new_value',
    'old_value',
    'target_id',
  };
}

