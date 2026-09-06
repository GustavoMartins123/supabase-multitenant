//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RenameProjectResponse {
  /// Returns a new [RenameProjectResponse] instance.
  RenameProjectResponse({
    required this.action,
    required this.attempt,
    required this.createdAt,
    required this.createdBy,
    required this.currentStep,
    required this.errorCode,
    required this.finishedAt,
    required this.isIdempotent,
    required this.jobId,
    required this.message,
    required this.newName,
    required this.oldName,
    required this.progress,
    required this.project,
    required this.projectUuid,
    required this.queuePosition,
    required this.retryOf,
    required this.retryable,
    required this.startedAt,
    required this.status,
    required this.tenantUuid,
    required this.totalSteps,
    required this.updatedAt,
  });

  String action;

  int attempt;

  String? createdAt;

  String? createdBy;

  String? currentStep;

  String? errorCode;

  String? finishedAt;

  bool isIdempotent;

  String jobId;

  String? message;

  String newName;

  String oldName;

  int? progress;

  String project;

  String? projectUuid;

  int queuePosition;

  String? retryOf;

  bool retryable;

  String? startedAt;

  String status;

  String? tenantUuid;

  int? totalSteps;

  String? updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RenameProjectResponse &&
    other.action == action &&
    other.attempt == attempt &&
    other.createdAt == createdAt &&
    other.createdBy == createdBy &&
    other.currentStep == currentStep &&
    other.errorCode == errorCode &&
    other.finishedAt == finishedAt &&
    other.isIdempotent == isIdempotent &&
    other.jobId == jobId &&
    other.message == message &&
    other.newName == newName &&
    other.oldName == oldName &&
    other.progress == progress &&
    other.project == project &&
    other.projectUuid == projectUuid &&
    other.queuePosition == queuePosition &&
    other.retryOf == retryOf &&
    other.retryable == retryable &&
    other.startedAt == startedAt &&
    other.status == status &&
    other.tenantUuid == tenantUuid &&
    other.totalSteps == totalSteps &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (action.hashCode) +
    (attempt.hashCode) +
    (createdAt == null ? 0 : createdAt!.hashCode) +
    (createdBy == null ? 0 : createdBy!.hashCode) +
    (currentStep == null ? 0 : currentStep!.hashCode) +
    (errorCode == null ? 0 : errorCode!.hashCode) +
    (finishedAt == null ? 0 : finishedAt!.hashCode) +
    (isIdempotent.hashCode) +
    (jobId.hashCode) +
    (message == null ? 0 : message!.hashCode) +
    (newName.hashCode) +
    (oldName.hashCode) +
    (progress == null ? 0 : progress!.hashCode) +
    (project.hashCode) +
    (projectUuid == null ? 0 : projectUuid!.hashCode) +
    (queuePosition.hashCode) +
    (retryOf == null ? 0 : retryOf!.hashCode) +
    (retryable.hashCode) +
    (startedAt == null ? 0 : startedAt!.hashCode) +
    (status.hashCode) +
    (tenantUuid == null ? 0 : tenantUuid!.hashCode) +
    (totalSteps == null ? 0 : totalSteps!.hashCode) +
    (updatedAt == null ? 0 : updatedAt!.hashCode);

  @override
  String toString() => 'RenameProjectResponse[action=$action, attempt=$attempt, createdAt=$createdAt, createdBy=$createdBy, currentStep=$currentStep, errorCode=$errorCode, finishedAt=$finishedAt, isIdempotent=$isIdempotent, jobId=$jobId, message=$message, newName=$newName, oldName=$oldName, progress=$progress, project=$project, projectUuid=$projectUuid, queuePosition=$queuePosition, retryOf=$retryOf, retryable=$retryable, startedAt=$startedAt, status=$status, tenantUuid=$tenantUuid, totalSteps=$totalSteps, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'action'] = this.action;
      json[r'attempt'] = this.attempt;
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
    if (this.currentStep != null) {
      json[r'current_step'] = this.currentStep;
    } else {
      json[r'current_step'] = null;
    }
    if (this.errorCode != null) {
      json[r'error_code'] = this.errorCode;
    } else {
      json[r'error_code'] = null;
    }
    if (this.finishedAt != null) {
      json[r'finished_at'] = this.finishedAt;
    } else {
      json[r'finished_at'] = null;
    }
      json[r'is_idempotent'] = this.isIdempotent;
      json[r'job_id'] = this.jobId;
    if (this.message != null) {
      json[r'message'] = this.message;
    } else {
      json[r'message'] = null;
    }
      json[r'new_name'] = this.newName;
      json[r'old_name'] = this.oldName;
    if (this.progress != null) {
      json[r'progress'] = this.progress;
    } else {
      json[r'progress'] = null;
    }
      json[r'project'] = this.project;
    if (this.projectUuid != null) {
      json[r'project_uuid'] = this.projectUuid;
    } else {
      json[r'project_uuid'] = null;
    }
      json[r'queue_position'] = this.queuePosition;
    if (this.retryOf != null) {
      json[r'retry_of'] = this.retryOf;
    } else {
      json[r'retry_of'] = null;
    }
      json[r'retryable'] = this.retryable;
    if (this.startedAt != null) {
      json[r'started_at'] = this.startedAt;
    } else {
      json[r'started_at'] = null;
    }
      json[r'status'] = this.status;
    if (this.tenantUuid != null) {
      json[r'tenant_uuid'] = this.tenantUuid;
    } else {
      json[r'tenant_uuid'] = null;
    }
    if (this.totalSteps != null) {
      json[r'total_steps'] = this.totalSteps;
    } else {
      json[r'total_steps'] = null;
    }
    if (this.updatedAt != null) {
      json[r'updated_at'] = this.updatedAt;
    } else {
      json[r'updated_at'] = null;
    }
    return json;
  }

  /// Returns a new [RenameProjectResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RenameProjectResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RenameProjectResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RenameProjectResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RenameProjectResponse(
        action: mapValueOfType<String>(json, r'action')!,
        attempt: mapValueOfType<int>(json, r'attempt')!,
        createdAt: mapValueOfType<String>(json, r'created_at'),
        createdBy: mapValueOfType<String>(json, r'created_by'),
        currentStep: mapValueOfType<String>(json, r'current_step'),
        errorCode: mapValueOfType<String>(json, r'error_code'),
        finishedAt: mapValueOfType<String>(json, r'finished_at'),
        isIdempotent: mapValueOfType<bool>(json, r'is_idempotent')!,
        jobId: mapValueOfType<String>(json, r'job_id')!,
        message: mapValueOfType<String>(json, r'message'),
        newName: mapValueOfType<String>(json, r'new_name')!,
        oldName: mapValueOfType<String>(json, r'old_name')!,
        progress: mapValueOfType<int>(json, r'progress'),
        project: mapValueOfType<String>(json, r'project')!,
        projectUuid: mapValueOfType<String>(json, r'project_uuid'),
        queuePosition: mapValueOfType<int>(json, r'queue_position')!,
        retryOf: mapValueOfType<String>(json, r'retry_of'),
        retryable: mapValueOfType<bool>(json, r'retryable')!,
        startedAt: mapValueOfType<String>(json, r'started_at'),
        status: mapValueOfType<String>(json, r'status')!,
        tenantUuid: mapValueOfType<String>(json, r'tenant_uuid'),
        totalSteps: mapValueOfType<int>(json, r'total_steps'),
        updatedAt: mapValueOfType<String>(json, r'updated_at'),
      );
    }
    return null;
  }

  static List<RenameProjectResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RenameProjectResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RenameProjectResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RenameProjectResponse> mapFromJson(dynamic json) {
    final map = <String, RenameProjectResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RenameProjectResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RenameProjectResponse-objects as value to a dart map
  static Map<String, List<RenameProjectResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RenameProjectResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RenameProjectResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'action',
    'attempt',
    'created_at',
    'created_by',
    'current_step',
    'error_code',
    'finished_at',
    'is_idempotent',
    'job_id',
    'message',
    'new_name',
    'old_name',
    'progress',
    'project',
    'project_uuid',
    'queue_position',
    'retry_of',
    'retryable',
    'started_at',
    'status',
    'tenant_uuid',
    'total_steps',
    'updated_at',
  };
}

