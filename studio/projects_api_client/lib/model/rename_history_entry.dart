//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RenameHistoryEntry {
  /// Returns a new [RenameHistoryEntry] instance.
  RenameHistoryEntry({
    required this.actorName,
    required this.actorUserId,
    required this.completedAt,
    required this.createdAt,
    required this.error,
    required this.id,
    required this.jobId,
    required this.newName,
    required this.newPath,
    required this.oldName,
    required this.oldPath,
    required this.status,
    required this.updatedAt,
  });

  String actorName;

  String? actorUserId;

  String? completedAt;

  String createdAt;

  String? error;

  int id;

  String jobId;

  String newName;

  String newPath;

  String oldName;

  String oldPath;

  String status;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RenameHistoryEntry &&
    other.actorName == actorName &&
    other.actorUserId == actorUserId &&
    other.completedAt == completedAt &&
    other.createdAt == createdAt &&
    other.error == error &&
    other.id == id &&
    other.jobId == jobId &&
    other.newName == newName &&
    other.newPath == newPath &&
    other.oldName == oldName &&
    other.oldPath == oldPath &&
    other.status == status &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (actorName.hashCode) +
    (actorUserId == null ? 0 : actorUserId!.hashCode) +
    (completedAt == null ? 0 : completedAt!.hashCode) +
    (createdAt.hashCode) +
    (error == null ? 0 : error!.hashCode) +
    (id.hashCode) +
    (jobId.hashCode) +
    (newName.hashCode) +
    (newPath.hashCode) +
    (oldName.hashCode) +
    (oldPath.hashCode) +
    (status.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'RenameHistoryEntry[actorName=$actorName, actorUserId=$actorUserId, completedAt=$completedAt, createdAt=$createdAt, error=$error, id=$id, jobId=$jobId, newName=$newName, newPath=$newPath, oldName=$oldName, oldPath=$oldPath, status=$status, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'actor_name'] = this.actorName;
    if (this.actorUserId != null) {
      json[r'actor_user_id'] = this.actorUserId;
    } else {
      json[r'actor_user_id'] = null;
    }
    if (this.completedAt != null) {
      json[r'completed_at'] = this.completedAt;
    } else {
      json[r'completed_at'] = null;
    }
      json[r'created_at'] = this.createdAt;
    if (this.error != null) {
      json[r'error'] = this.error;
    } else {
      json[r'error'] = null;
    }
      json[r'id'] = this.id;
      json[r'job_id'] = this.jobId;
      json[r'new_name'] = this.newName;
      json[r'new_path'] = this.newPath;
      json[r'old_name'] = this.oldName;
      json[r'old_path'] = this.oldPath;
      json[r'status'] = this.status;
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [RenameHistoryEntry] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RenameHistoryEntry? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RenameHistoryEntry[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RenameHistoryEntry[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RenameHistoryEntry(
        actorName: mapValueOfType<String>(json, r'actor_name')!,
        actorUserId: mapValueOfType<String>(json, r'actor_user_id'),
        completedAt: mapValueOfType<String>(json, r'completed_at'),
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        error: mapValueOfType<String>(json, r'error'),
        id: mapValueOfType<int>(json, r'id')!,
        jobId: mapValueOfType<String>(json, r'job_id')!,
        newName: mapValueOfType<String>(json, r'new_name')!,
        newPath: mapValueOfType<String>(json, r'new_path')!,
        oldName: mapValueOfType<String>(json, r'old_name')!,
        oldPath: mapValueOfType<String>(json, r'old_path')!,
        status: mapValueOfType<String>(json, r'status')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<RenameHistoryEntry> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RenameHistoryEntry>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RenameHistoryEntry.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RenameHistoryEntry> mapFromJson(dynamic json) {
    final map = <String, RenameHistoryEntry>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RenameHistoryEntry.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RenameHistoryEntry-objects as value to a dart map
  static Map<String, List<RenameHistoryEntry>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RenameHistoryEntry>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RenameHistoryEntry.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'actor_name',
    'actor_user_id',
    'completed_at',
    'created_at',
    'error',
    'id',
    'job_id',
    'new_name',
    'new_path',
    'old_name',
    'old_path',
    'status',
    'updated_at',
  };
}

