//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class StudioContextResponse {
  /// Returns a new [StudioContextResponse] instance.
  StudioContextResponse({
    required this.anonKey,
    required this.displayName,
    required this.fileSizeLimit,
    required this.projectKeyVersion,
    required this.projectUuid,
    required this.ref,
    required this.role,
    required this.tenantUuid,
  });

  String anonKey;

  String displayName;

  int fileSizeLimit;

  int? projectKeyVersion;

  String projectUuid;

  String ref;

  String? role;

  String? tenantUuid;

  @override
  bool operator ==(Object other) => identical(this, other) || other is StudioContextResponse &&
    other.anonKey == anonKey &&
    other.displayName == displayName &&
    other.fileSizeLimit == fileSizeLimit &&
    other.projectKeyVersion == projectKeyVersion &&
    other.projectUuid == projectUuid &&
    other.ref == ref &&
    other.role == role &&
    other.tenantUuid == tenantUuid;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (anonKey.hashCode) +
    (displayName.hashCode) +
    (fileSizeLimit.hashCode) +
    (projectKeyVersion == null ? 0 : projectKeyVersion!.hashCode) +
    (projectUuid.hashCode) +
    (ref.hashCode) +
    (role == null ? 0 : role!.hashCode) +
    (tenantUuid == null ? 0 : tenantUuid!.hashCode);

  @override
  String toString() => 'StudioContextResponse[anonKey=$anonKey, displayName=$displayName, fileSizeLimit=$fileSizeLimit, projectKeyVersion=$projectKeyVersion, projectUuid=$projectUuid, ref=$ref, role=$role, tenantUuid=$tenantUuid]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'anon_key'] = this.anonKey;
      json[r'display_name'] = this.displayName;
      json[r'file_size_limit'] = this.fileSizeLimit;
    if (this.projectKeyVersion != null) {
      json[r'project_key_version'] = this.projectKeyVersion;
    } else {
      json[r'project_key_version'] = null;
    }
      json[r'project_uuid'] = this.projectUuid;
      json[r'ref'] = this.ref;
    if (this.role != null) {
      json[r'role'] = this.role;
    } else {
      json[r'role'] = null;
    }
    if (this.tenantUuid != null) {
      json[r'tenant_uuid'] = this.tenantUuid;
    } else {
      json[r'tenant_uuid'] = null;
    }
    return json;
  }

  /// Returns a new [StudioContextResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static StudioContextResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "StudioContextResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "StudioContextResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return StudioContextResponse(
        anonKey: mapValueOfType<String>(json, r'anon_key')!,
        displayName: mapValueOfType<String>(json, r'display_name')!,
        fileSizeLimit: mapValueOfType<int>(json, r'file_size_limit')!,
        projectKeyVersion: mapValueOfType<int>(json, r'project_key_version'),
        projectUuid: mapValueOfType<String>(json, r'project_uuid')!,
        ref: mapValueOfType<String>(json, r'ref')!,
        role: mapValueOfType<String>(json, r'role'),
        tenantUuid: mapValueOfType<String>(json, r'tenant_uuid'),
      );
    }
    return null;
  }

  static List<StudioContextResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <StudioContextResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = StudioContextResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, StudioContextResponse> mapFromJson(dynamic json) {
    final map = <String, StudioContextResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = StudioContextResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of StudioContextResponse-objects as value to a dart map
  static Map<String, List<StudioContextResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<StudioContextResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = StudioContextResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'anon_key',
    'display_name',
    'file_size_limit',
    'project_key_version',
    'project_uuid',
    'ref',
    'role',
    'tenant_uuid',
  };
}

