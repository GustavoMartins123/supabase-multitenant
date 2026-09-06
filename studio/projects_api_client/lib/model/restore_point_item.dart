//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RestorePointItem {
  /// Returns a new [RestorePointItem] instance.
  RestorePointItem({
    required this.completedAt,
    required this.createdAt,
    required this.createdBy,
    required this.createdByName,
    required this.description,
    required this.error,
    required this.id,
    required this.isAutomatic,
    required this.jobId,
    required this.lastRestoredAt,
    required this.projectRefAtCreation,
    required this.restoreCount,
    required this.sizeBytes,
    required this.status,
    required this.title,
  });

  String? completedAt;

  String? createdAt;

  String? createdBy;

  String createdByName;

  String? description;

  String? error;

  String id;

  bool isAutomatic;

  String? jobId;

  String? lastRestoredAt;

  String projectRefAtCreation;

  int restoreCount;

  int? sizeBytes;

  String status;

  String title;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RestorePointItem &&
    other.completedAt == completedAt &&
    other.createdAt == createdAt &&
    other.createdBy == createdBy &&
    other.createdByName == createdByName &&
    other.description == description &&
    other.error == error &&
    other.id == id &&
    other.isAutomatic == isAutomatic &&
    other.jobId == jobId &&
    other.lastRestoredAt == lastRestoredAt &&
    other.projectRefAtCreation == projectRefAtCreation &&
    other.restoreCount == restoreCount &&
    other.sizeBytes == sizeBytes &&
    other.status == status &&
    other.title == title;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (completedAt == null ? 0 : completedAt!.hashCode) +
    (createdAt == null ? 0 : createdAt!.hashCode) +
    (createdBy == null ? 0 : createdBy!.hashCode) +
    (createdByName.hashCode) +
    (description == null ? 0 : description!.hashCode) +
    (error == null ? 0 : error!.hashCode) +
    (id.hashCode) +
    (isAutomatic.hashCode) +
    (jobId == null ? 0 : jobId!.hashCode) +
    (lastRestoredAt == null ? 0 : lastRestoredAt!.hashCode) +
    (projectRefAtCreation.hashCode) +
    (restoreCount.hashCode) +
    (sizeBytes == null ? 0 : sizeBytes!.hashCode) +
    (status.hashCode) +
    (title.hashCode);

  @override
  String toString() => 'RestorePointItem[completedAt=$completedAt, createdAt=$createdAt, createdBy=$createdBy, createdByName=$createdByName, description=$description, error=$error, id=$id, isAutomatic=$isAutomatic, jobId=$jobId, lastRestoredAt=$lastRestoredAt, projectRefAtCreation=$projectRefAtCreation, restoreCount=$restoreCount, sizeBytes=$sizeBytes, status=$status, title=$title]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.completedAt != null) {
      json[r'completed_at'] = this.completedAt;
    } else {
      json[r'completed_at'] = null;
    }
    if (this.createdAt != null) {
      json[r'created_at'] = this.createdAt;
    } else {
      json[r'created_at'] = null;
    }
    if (this.createdBy != null) {
      json[r'created_by'] = this.createdBy;
    } else {
      json[r'created_by'] = null;
    }
      json[r'created_by_name'] = this.createdByName;
    if (this.description != null) {
      json[r'description'] = this.description;
    } else {
      json[r'description'] = null;
    }
    if (this.error != null) {
      json[r'error'] = this.error;
    } else {
      json[r'error'] = null;
    }
      json[r'id'] = this.id;
      json[r'is_automatic'] = this.isAutomatic;
    if (this.jobId != null) {
      json[r'job_id'] = this.jobId;
    } else {
      json[r'job_id'] = null;
    }
    if (this.lastRestoredAt != null) {
      json[r'last_restored_at'] = this.lastRestoredAt;
    } else {
      json[r'last_restored_at'] = null;
    }
      json[r'project_ref_at_creation'] = this.projectRefAtCreation;
      json[r'restore_count'] = this.restoreCount;
    if (this.sizeBytes != null) {
      json[r'size_bytes'] = this.sizeBytes;
    } else {
      json[r'size_bytes'] = null;
    }
      json[r'status'] = this.status;
      json[r'title'] = this.title;
    return json;
  }

  /// Returns a new [RestorePointItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RestorePointItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RestorePointItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RestorePointItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RestorePointItem(
        completedAt: mapValueOfType<String>(json, r'completed_at'),
        createdAt: mapValueOfType<String>(json, r'created_at'),
        createdBy: mapValueOfType<String>(json, r'created_by'),
        createdByName: mapValueOfType<String>(json, r'created_by_name')!,
        description: mapValueOfType<String>(json, r'description'),
        error: mapValueOfType<String>(json, r'error'),
        id: mapValueOfType<String>(json, r'id')!,
        isAutomatic: mapValueOfType<bool>(json, r'is_automatic')!,
        jobId: mapValueOfType<String>(json, r'job_id'),
        lastRestoredAt: mapValueOfType<String>(json, r'last_restored_at'),
        projectRefAtCreation: mapValueOfType<String>(json, r'project_ref_at_creation')!,
        restoreCount: mapValueOfType<int>(json, r'restore_count')!,
        sizeBytes: mapValueOfType<int>(json, r'size_bytes'),
        status: mapValueOfType<String>(json, r'status')!,
        title: mapValueOfType<String>(json, r'title')!,
      );
    }
    return null;
  }

  static List<RestorePointItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RestorePointItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RestorePointItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RestorePointItem> mapFromJson(dynamic json) {
    final map = <String, RestorePointItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RestorePointItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RestorePointItem-objects as value to a dart map
  static Map<String, List<RestorePointItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RestorePointItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RestorePointItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'completed_at',
    'created_at',
    'created_by',
    'created_by_name',
    'description',
    'error',
    'id',
    'is_automatic',
    'job_id',
    'last_restored_at',
    'project_ref_at_creation',
    'restore_count',
    'size_bytes',
    'status',
    'title',
  };
}

