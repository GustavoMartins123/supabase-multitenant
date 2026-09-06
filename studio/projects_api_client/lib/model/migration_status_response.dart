//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class MigrationStatusResponse {
  /// Returns a new [MigrationStatusResponse] instance.
  MigrationStatusResponse({
    required this.activatedAt,
    required this.apiKeysetVersion,
    required this.confirmedPendingKeyCount,
    required this.cutoverStartedAt,
    required this.gatewayReadyAt,
    required this.pendingKeyCount,
    required this.preparedAt,
    required this.project,
    required this.status,
  });

  String? activatedAt;

  int apiKeysetVersion;

  int confirmedPendingKeyCount;

  String? cutoverStartedAt;

  String? gatewayReadyAt;

  int pendingKeyCount;

  String? preparedAt;

  String project;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is MigrationStatusResponse &&
    other.activatedAt == activatedAt &&
    other.apiKeysetVersion == apiKeysetVersion &&
    other.confirmedPendingKeyCount == confirmedPendingKeyCount &&
    other.cutoverStartedAt == cutoverStartedAt &&
    other.gatewayReadyAt == gatewayReadyAt &&
    other.pendingKeyCount == pendingKeyCount &&
    other.preparedAt == preparedAt &&
    other.project == project &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (activatedAt == null ? 0 : activatedAt!.hashCode) +
    (apiKeysetVersion.hashCode) +
    (confirmedPendingKeyCount.hashCode) +
    (cutoverStartedAt == null ? 0 : cutoverStartedAt!.hashCode) +
    (gatewayReadyAt == null ? 0 : gatewayReadyAt!.hashCode) +
    (pendingKeyCount.hashCode) +
    (preparedAt == null ? 0 : preparedAt!.hashCode) +
    (project.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'MigrationStatusResponse[activatedAt=$activatedAt, apiKeysetVersion=$apiKeysetVersion, confirmedPendingKeyCount=$confirmedPendingKeyCount, cutoverStartedAt=$cutoverStartedAt, gatewayReadyAt=$gatewayReadyAt, pendingKeyCount=$pendingKeyCount, preparedAt=$preparedAt, project=$project, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.activatedAt != null) {
      json[r'activated_at'] = this.activatedAt;
    } else {
      json[r'activated_at'] = null;
    }
      json[r'api_keyset_version'] = this.apiKeysetVersion;
      json[r'confirmed_pending_key_count'] = this.confirmedPendingKeyCount;
    if (this.cutoverStartedAt != null) {
      json[r'cutover_started_at'] = this.cutoverStartedAt;
    } else {
      json[r'cutover_started_at'] = null;
    }
    if (this.gatewayReadyAt != null) {
      json[r'gateway_ready_at'] = this.gatewayReadyAt;
    } else {
      json[r'gateway_ready_at'] = null;
    }
      json[r'pending_key_count'] = this.pendingKeyCount;
    if (this.preparedAt != null) {
      json[r'prepared_at'] = this.preparedAt;
    } else {
      json[r'prepared_at'] = null;
    }
      json[r'project'] = this.project;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [MigrationStatusResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static MigrationStatusResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "MigrationStatusResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "MigrationStatusResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return MigrationStatusResponse(
        activatedAt: mapValueOfType<String>(json, r'activated_at'),
        apiKeysetVersion: mapValueOfType<int>(json, r'api_keyset_version')!,
        confirmedPendingKeyCount: mapValueOfType<int>(json, r'confirmed_pending_key_count')!,
        cutoverStartedAt: mapValueOfType<String>(json, r'cutover_started_at'),
        gatewayReadyAt: mapValueOfType<String>(json, r'gateway_ready_at'),
        pendingKeyCount: mapValueOfType<int>(json, r'pending_key_count')!,
        preparedAt: mapValueOfType<String>(json, r'prepared_at'),
        project: mapValueOfType<String>(json, r'project')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<MigrationStatusResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <MigrationStatusResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = MigrationStatusResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, MigrationStatusResponse> mapFromJson(dynamic json) {
    final map = <String, MigrationStatusResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = MigrationStatusResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of MigrationStatusResponse-objects as value to a dart map
  static Map<String, List<MigrationStatusResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<MigrationStatusResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = MigrationStatusResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'activated_at',
    'api_keyset_version',
    'confirmed_pending_key_count',
    'cutover_started_at',
    'gateway_ready_at',
    'pending_key_count',
    'prepared_at',
    'project',
    'status',
  };
}

