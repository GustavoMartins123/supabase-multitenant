//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectStatusResponse {
  /// Returns a new [ProjectStatusResponse] instance.
  ProjectStatusResponse({
    this.agentOffline,
    this.containers = const [],
    required this.running,
    required this.status,
    required this.total,
  });

  bool? agentOffline;

  List<ContainerInfoItem>? containers;

  int running;

  String status;

  int total;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectStatusResponse &&
    other.agentOffline == agentOffline &&
    _deepEquality.equals(other.containers, containers) &&
    other.running == running &&
    other.status == status &&
    other.total == total;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (agentOffline == null ? 0 : agentOffline!.hashCode) +
    (containers == null ? 0 : containers!.hashCode) +
    (running.hashCode) +
    (status.hashCode) +
    (total.hashCode);

  @override
  String toString() => 'ProjectStatusResponse[agentOffline=$agentOffline, containers=$containers, running=$running, status=$status, total=$total]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.agentOffline != null) {
      json[r'agent_offline'] = this.agentOffline;
    } else {
      json[r'agent_offline'] = null;
    }
    if (this.containers != null) {
      json[r'containers'] = this.containers;
    } else {
      json[r'containers'] = null;
    }
      json[r'running'] = this.running;
      json[r'status'] = this.status;
      json[r'total'] = this.total;
    return json;
  }

  /// Returns a new [ProjectStatusResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectStatusResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectStatusResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectStatusResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectStatusResponse(
        agentOffline: mapValueOfType<bool>(json, r'agent_offline'),
        containers: ContainerInfoItem.listFromJson(json[r'containers']),
        running: mapValueOfType<int>(json, r'running')!,
        status: mapValueOfType<String>(json, r'status')!,
        total: mapValueOfType<int>(json, r'total')!,
      );
    }
    return null;
  }

  static List<ProjectStatusResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectStatusResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectStatusResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectStatusResponse> mapFromJson(dynamic json) {
    final map = <String, ProjectStatusResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectStatusResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectStatusResponse-objects as value to a dart map
  static Map<String, List<ProjectStatusResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectStatusResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectStatusResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'running',
    'status',
    'total',
  };
}

