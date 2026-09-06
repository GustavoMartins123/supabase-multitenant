//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectQueueInFlightJob {
  /// Returns a new [ProjectQueueInFlightJob] instance.
  ProjectQueueInFlightJob({
    required this.action,
    required this.currentStep,
    required this.jobId,
    required this.message,
    required this.progress,
    required this.status,
    required this.totalSteps,
    required this.updatedAt,
  });

  String action;

  String? currentStep;

  String jobId;

  String? message;

  int? progress;

  String status;

  int? totalSteps;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectQueueInFlightJob &&
    other.action == action &&
    other.currentStep == currentStep &&
    other.jobId == jobId &&
    other.message == message &&
    other.progress == progress &&
    other.status == status &&
    other.totalSteps == totalSteps &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (action.hashCode) +
    (currentStep == null ? 0 : currentStep!.hashCode) +
    (jobId.hashCode) +
    (message == null ? 0 : message!.hashCode) +
    (progress == null ? 0 : progress!.hashCode) +
    (status.hashCode) +
    (totalSteps == null ? 0 : totalSteps!.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'ProjectQueueInFlightJob[action=$action, currentStep=$currentStep, jobId=$jobId, message=$message, progress=$progress, status=$status, totalSteps=$totalSteps, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'action'] = this.action;
    if (this.currentStep != null) {
      json[r'current_step'] = this.currentStep;
    } else {
      json[r'current_step'] = null;
    }
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
      json[r'status'] = this.status;
    if (this.totalSteps != null) {
      json[r'total_steps'] = this.totalSteps;
    } else {
      json[r'total_steps'] = null;
    }
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [ProjectQueueInFlightJob] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectQueueInFlightJob? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectQueueInFlightJob[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectQueueInFlightJob[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectQueueInFlightJob(
        action: mapValueOfType<String>(json, r'action')!,
        currentStep: mapValueOfType<String>(json, r'current_step'),
        jobId: mapValueOfType<String>(json, r'job_id')!,
        message: mapValueOfType<String>(json, r'message'),
        progress: mapValueOfType<int>(json, r'progress'),
        status: mapValueOfType<String>(json, r'status')!,
        totalSteps: mapValueOfType<int>(json, r'total_steps'),
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<ProjectQueueInFlightJob> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectQueueInFlightJob>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectQueueInFlightJob.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectQueueInFlightJob> mapFromJson(dynamic json) {
    final map = <String, ProjectQueueInFlightJob>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectQueueInFlightJob.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectQueueInFlightJob-objects as value to a dart map
  static Map<String, List<ProjectQueueInFlightJob>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectQueueInFlightJob>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectQueueInFlightJob.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'action',
    'current_step',
    'job_id',
    'message',
    'progress',
    'status',
    'total_steps',
    'updated_at',
  };
}

