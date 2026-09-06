//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class JobResponse {
  /// Returns a new [JobResponse] instance.
  JobResponse({
    required this.action,
    this.attempt = 1,
    this.createdAt,
    this.createdBy,
    this.currentStep,
    this.errorCode,
    this.finishedAt,
    this.isIdempotent = false,
    required this.jobId,
    this.message,
    this.progress,
    required this.project,
    this.projectUuid,
    this.retryOf,
    this.retryable = false,
    this.startedAt,
    required this.status,
    this.stderrTail,
    this.stdoutTail,
    this.tenantUuid,
    this.totalSteps,
    this.updatedAt,
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

  int? progress;

  String project;

  String? projectUuid;

  String? retryOf;

  bool retryable;

  String? startedAt;

  String status;

  String? stderrTail;

  String? stdoutTail;

  String? tenantUuid;

  int? totalSteps;

  String? updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is JobResponse &&
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
    other.progress == progress &&
    other.project == project &&
    other.projectUuid == projectUuid &&
    other.retryOf == retryOf &&
    other.retryable == retryable &&
    other.startedAt == startedAt &&
    other.status == status &&
    other.stderrTail == stderrTail &&
    other.stdoutTail == stdoutTail &&
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
    (progress == null ? 0 : progress!.hashCode) +
    (project.hashCode) +
    (projectUuid == null ? 0 : projectUuid!.hashCode) +
    (retryOf == null ? 0 : retryOf!.hashCode) +
    (retryable.hashCode) +
    (startedAt == null ? 0 : startedAt!.hashCode) +
    (status.hashCode) +
    (stderrTail == null ? 0 : stderrTail!.hashCode) +
    (stdoutTail == null ? 0 : stdoutTail!.hashCode) +
    (tenantUuid == null ? 0 : tenantUuid!.hashCode) +
    (totalSteps == null ? 0 : totalSteps!.hashCode) +
    (updatedAt == null ? 0 : updatedAt!.hashCode);

  @override
  String toString() => 'JobResponse[action=$action, attempt=$attempt, createdAt=$createdAt, createdBy=$createdBy, currentStep=$currentStep, errorCode=$errorCode, finishedAt=$finishedAt, isIdempotent=$isIdempotent, jobId=$jobId, message=$message, progress=$progress, project=$project, projectUuid=$projectUuid, retryOf=$retryOf, retryable=$retryable, startedAt=$startedAt, status=$status, stderrTail=$stderrTail, stdoutTail=$stdoutTail, tenantUuid=$tenantUuid, totalSteps=$totalSteps, updatedAt=$updatedAt]';

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
    if (this.stderrTail != null) {
      json[r'stderr_tail'] = this.stderrTail;
    } else {
      json[r'stderr_tail'] = null;
    }
    if (this.stdoutTail != null) {
      json[r'stdout_tail'] = this.stdoutTail;
    } else {
      json[r'stdout_tail'] = null;
    }
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

  /// Returns a new [JobResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static JobResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "JobResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "JobResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return JobResponse(
        action: mapValueOfType<String>(json, r'action')!,
        attempt: mapValueOfType<int>(json, r'attempt') ?? 1,
        createdAt: mapValueOfType<String>(json, r'created_at'),
        createdBy: mapValueOfType<String>(json, r'created_by'),
        currentStep: mapValueOfType<String>(json, r'current_step'),
        errorCode: mapValueOfType<String>(json, r'error_code'),
        finishedAt: mapValueOfType<String>(json, r'finished_at'),
        isIdempotent: mapValueOfType<bool>(json, r'is_idempotent') ?? false,
        jobId: mapValueOfType<String>(json, r'job_id')!,
        message: mapValueOfType<String>(json, r'message'),
        progress: mapValueOfType<int>(json, r'progress'),
        project: mapValueOfType<String>(json, r'project')!,
        projectUuid: mapValueOfType<String>(json, r'project_uuid'),
        retryOf: mapValueOfType<String>(json, r'retry_of'),
        retryable: mapValueOfType<bool>(json, r'retryable') ?? false,
        startedAt: mapValueOfType<String>(json, r'started_at'),
        status: mapValueOfType<String>(json, r'status')!,
        stderrTail: mapValueOfType<String>(json, r'stderr_tail'),
        stdoutTail: mapValueOfType<String>(json, r'stdout_tail'),
        tenantUuid: mapValueOfType<String>(json, r'tenant_uuid'),
        totalSteps: mapValueOfType<int>(json, r'total_steps'),
        updatedAt: mapValueOfType<String>(json, r'updated_at'),
      );
    }
    return null;
  }

  static List<JobResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <JobResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = JobResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, JobResponse> mapFromJson(dynamic json) {
    final map = <String, JobResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = JobResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of JobResponse-objects as value to a dart map
  static Map<String, List<JobResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<JobResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = JobResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'action',
    'job_id',
    'project',
    'status',
  };
}

