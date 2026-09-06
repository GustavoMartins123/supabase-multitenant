//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ProjectListItem {
  /// Returns a new [ProjectListItem] instance.
  ProjectListItem({
    required this.automaticKeyRotationBlocked,
    required this.automaticKeyRotationDueAt,
    required this.automaticKeyRotationEnabled,
    required this.automaticKeyRotationLastError,
    required this.automaticKeyRotationLeadDays,
    required this.displayName,
    required this.fileSizeLimit,
    required this.internalTokenExpired,
    required this.internalTokenExpiresAt,
    required this.internalTokenExpiringSoon,
    required this.internalTokenExpiryWarningDays,
    required this.lastKeyRotationAt,
    required this.name,
    required this.opaqueApiKeySlotCount,
    required this.opaqueApiKeysStatus,
    required this.projectUuid,
    required this.storageLimitToken,
    required this.tenantUuid,
  });

  bool automaticKeyRotationBlocked;

  int? automaticKeyRotationDueAt;

  bool automaticKeyRotationEnabled;

  String? automaticKeyRotationLastError;

  int automaticKeyRotationLeadDays;

  String? displayName;

  String fileSizeLimit;

  bool internalTokenExpired;

  int? internalTokenExpiresAt;

  bool internalTokenExpiringSoon;

  int internalTokenExpiryWarningDays;

  String? lastKeyRotationAt;

  String name;

  int opaqueApiKeySlotCount;

  String opaqueApiKeysStatus;

  String projectUuid;

  String storageLimitToken;

  String? tenantUuid;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ProjectListItem &&
    other.automaticKeyRotationBlocked == automaticKeyRotationBlocked &&
    other.automaticKeyRotationDueAt == automaticKeyRotationDueAt &&
    other.automaticKeyRotationEnabled == automaticKeyRotationEnabled &&
    other.automaticKeyRotationLastError == automaticKeyRotationLastError &&
    other.automaticKeyRotationLeadDays == automaticKeyRotationLeadDays &&
    other.displayName == displayName &&
    other.fileSizeLimit == fileSizeLimit &&
    other.internalTokenExpired == internalTokenExpired &&
    other.internalTokenExpiresAt == internalTokenExpiresAt &&
    other.internalTokenExpiringSoon == internalTokenExpiringSoon &&
    other.internalTokenExpiryWarningDays == internalTokenExpiryWarningDays &&
    other.lastKeyRotationAt == lastKeyRotationAt &&
    other.name == name &&
    other.opaqueApiKeySlotCount == opaqueApiKeySlotCount &&
    other.opaqueApiKeysStatus == opaqueApiKeysStatus &&
    other.projectUuid == projectUuid &&
    other.storageLimitToken == storageLimitToken &&
    other.tenantUuid == tenantUuid;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (automaticKeyRotationBlocked.hashCode) +
    (automaticKeyRotationDueAt == null ? 0 : automaticKeyRotationDueAt!.hashCode) +
    (automaticKeyRotationEnabled.hashCode) +
    (automaticKeyRotationLastError == null ? 0 : automaticKeyRotationLastError!.hashCode) +
    (automaticKeyRotationLeadDays.hashCode) +
    (displayName == null ? 0 : displayName!.hashCode) +
    (fileSizeLimit.hashCode) +
    (internalTokenExpired.hashCode) +
    (internalTokenExpiresAt == null ? 0 : internalTokenExpiresAt!.hashCode) +
    (internalTokenExpiringSoon.hashCode) +
    (internalTokenExpiryWarningDays.hashCode) +
    (lastKeyRotationAt == null ? 0 : lastKeyRotationAt!.hashCode) +
    (name.hashCode) +
    (opaqueApiKeySlotCount.hashCode) +
    (opaqueApiKeysStatus.hashCode) +
    (projectUuid.hashCode) +
    (storageLimitToken.hashCode) +
    (tenantUuid == null ? 0 : tenantUuid!.hashCode);

  @override
  String toString() => 'ProjectListItem[automaticKeyRotationBlocked=$automaticKeyRotationBlocked, automaticKeyRotationDueAt=$automaticKeyRotationDueAt, automaticKeyRotationEnabled=$automaticKeyRotationEnabled, automaticKeyRotationLastError=$automaticKeyRotationLastError, automaticKeyRotationLeadDays=$automaticKeyRotationLeadDays, displayName=$displayName, fileSizeLimit=$fileSizeLimit, internalTokenExpired=$internalTokenExpired, internalTokenExpiresAt=$internalTokenExpiresAt, internalTokenExpiringSoon=$internalTokenExpiringSoon, internalTokenExpiryWarningDays=$internalTokenExpiryWarningDays, lastKeyRotationAt=$lastKeyRotationAt, name=$name, opaqueApiKeySlotCount=$opaqueApiKeySlotCount, opaqueApiKeysStatus=$opaqueApiKeysStatus, projectUuid=$projectUuid, storageLimitToken=$storageLimitToken, tenantUuid=$tenantUuid]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'automatic_key_rotation_blocked'] = this.automaticKeyRotationBlocked;
    if (this.automaticKeyRotationDueAt != null) {
      json[r'automatic_key_rotation_due_at'] = this.automaticKeyRotationDueAt;
    } else {
      json[r'automatic_key_rotation_due_at'] = null;
    }
      json[r'automatic_key_rotation_enabled'] = this.automaticKeyRotationEnabled;
    if (this.automaticKeyRotationLastError != null) {
      json[r'automatic_key_rotation_last_error'] = this.automaticKeyRotationLastError;
    } else {
      json[r'automatic_key_rotation_last_error'] = null;
    }
      json[r'automatic_key_rotation_lead_days'] = this.automaticKeyRotationLeadDays;
    if (this.displayName != null) {
      json[r'display_name'] = this.displayName;
    } else {
      json[r'display_name'] = null;
    }
      json[r'file_size_limit'] = this.fileSizeLimit;
      json[r'internal_token_expired'] = this.internalTokenExpired;
    if (this.internalTokenExpiresAt != null) {
      json[r'internal_token_expires_at'] = this.internalTokenExpiresAt;
    } else {
      json[r'internal_token_expires_at'] = null;
    }
      json[r'internal_token_expiring_soon'] = this.internalTokenExpiringSoon;
      json[r'internal_token_expiry_warning_days'] = this.internalTokenExpiryWarningDays;
    if (this.lastKeyRotationAt != null) {
      json[r'last_key_rotation_at'] = this.lastKeyRotationAt;
    } else {
      json[r'last_key_rotation_at'] = null;
    }
      json[r'name'] = this.name;
      json[r'opaque_api_key_slot_count'] = this.opaqueApiKeySlotCount;
      json[r'opaque_api_keys_status'] = this.opaqueApiKeysStatus;
      json[r'project_uuid'] = this.projectUuid;
      json[r'storage_limit_token'] = this.storageLimitToken;
    if (this.tenantUuid != null) {
      json[r'tenant_uuid'] = this.tenantUuid;
    } else {
      json[r'tenant_uuid'] = null;
    }
    return json;
  }

  /// Returns a new [ProjectListItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ProjectListItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ProjectListItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ProjectListItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ProjectListItem(
        automaticKeyRotationBlocked: mapValueOfType<bool>(json, r'automatic_key_rotation_blocked')!,
        automaticKeyRotationDueAt: mapValueOfType<int>(json, r'automatic_key_rotation_due_at'),
        automaticKeyRotationEnabled: mapValueOfType<bool>(json, r'automatic_key_rotation_enabled')!,
        automaticKeyRotationLastError: mapValueOfType<String>(json, r'automatic_key_rotation_last_error'),
        automaticKeyRotationLeadDays: mapValueOfType<int>(json, r'automatic_key_rotation_lead_days')!,
        displayName: mapValueOfType<String>(json, r'display_name'),
        fileSizeLimit: mapValueOfType<String>(json, r'file_size_limit')!,
        internalTokenExpired: mapValueOfType<bool>(json, r'internal_token_expired')!,
        internalTokenExpiresAt: mapValueOfType<int>(json, r'internal_token_expires_at'),
        internalTokenExpiringSoon: mapValueOfType<bool>(json, r'internal_token_expiring_soon')!,
        internalTokenExpiryWarningDays: mapValueOfType<int>(json, r'internal_token_expiry_warning_days')!,
        lastKeyRotationAt: mapValueOfType<String>(json, r'last_key_rotation_at'),
        name: mapValueOfType<String>(json, r'name')!,
        opaqueApiKeySlotCount: mapValueOfType<int>(json, r'opaque_api_key_slot_count')!,
        opaqueApiKeysStatus: mapValueOfType<String>(json, r'opaque_api_keys_status')!,
        projectUuid: mapValueOfType<String>(json, r'project_uuid')!,
        storageLimitToken: mapValueOfType<String>(json, r'storage_limit_token')!,
        tenantUuid: mapValueOfType<String>(json, r'tenant_uuid'),
      );
    }
    return null;
  }

  static List<ProjectListItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ProjectListItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ProjectListItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ProjectListItem> mapFromJson(dynamic json) {
    final map = <String, ProjectListItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ProjectListItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ProjectListItem-objects as value to a dart map
  static Map<String, List<ProjectListItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ProjectListItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ProjectListItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'automatic_key_rotation_blocked',
    'automatic_key_rotation_due_at',
    'automatic_key_rotation_enabled',
    'automatic_key_rotation_last_error',
    'automatic_key_rotation_lead_days',
    'display_name',
    'file_size_limit',
    'internal_token_expired',
    'internal_token_expires_at',
    'internal_token_expiring_soon',
    'internal_token_expiry_warning_days',
    'last_key_rotation_at',
    'name',
    'opaque_api_key_slot_count',
    'opaque_api_keys_status',
    'project_uuid',
    'storage_limit_token',
    'tenant_uuid',
  };
}

