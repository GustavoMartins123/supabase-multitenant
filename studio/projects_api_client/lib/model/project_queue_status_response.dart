//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectQueueStatusResponse {
  /// Returns a new [ProjectQueueStatusResponse] instance.
  ProjectQueueStatusResponse({
    required this.currentJobId,
    this.inFlight = const [],
    required this.isBusy,
    required this.message,
    required this.project,
    required this.queued,
  });

  String? currentJobId;

  List<ProjectQueueInFlightJob> inFlight;

  bool isBusy;

  String message;

  String project;

  int queued;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectQueueStatusResponse &&
    other.currentJobId == currentJobId &&
    _deepEquality.equals(other.inFlight, inFlight) &&
    other.isBusy == isBusy &&
    other.message == message &&
    other.project == project &&
    other.queued == queued;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (currentJobId == null ? 0 : currentJobId!.hashCode) +
    (inFlight.hashCode) +
    (isBusy.hashCode) +
    (message.hashCode) +
    (project.hashCode) +
    (queued.hashCode);

  @override
  String toString() => 'ProjectQueueStatusResponse[currentJobId=$currentJobId, inFlight=$inFlight, isBusy=$isBusy, message=$message, project=$project, queued=$queued]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.currentJobId != null) {
      json[r'current_job_id'] = this.currentJobId;
    } else {
      json[r'current_job_id'] = null;
    }
      json[r'in_flight'] = this.inFlight;
      json[r'is_busy'] = this.isBusy;
      json[r'message'] = this.message;
      json[r'project'] = this.project;
      json[r'queued'] = this.queued;
    return json;
  }

  /// Returns a new [ProjectQueueStatusResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectQueueStatusResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectQueueStatusResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectQueueStatusResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectQueueStatusResponse(
        currentJobId: mapValueOfType<String>(json, r'current_job_id'),
        inFlight: ProjectQueueInFlightJob.listFromJson(json[r'in_flight']),
        isBusy: mapValueOfType<bool>(json, r'is_busy')!,
        message: mapValueOfType<String>(json, r'message')!,
        project: mapValueOfType<String>(json, r'project')!,
        queued: mapValueOfType<int>(json, r'queued')!,
      );
    }
    return null;
  }

  static List<ProjectQueueStatusResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectQueueStatusResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectQueueStatusResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectQueueStatusResponse> mapFromJson(dynamic json) {
    final map = <String, ProjectQueueStatusResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectQueueStatusResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectQueueStatusResponse-objects as value to a dart map
  static Map<String, List<ProjectQueueStatusResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectQueueStatusResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectQueueStatusResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'current_job_id',
    'in_flight',
    'is_busy',
    'message',
    'project',
    'queued',
  };
}

