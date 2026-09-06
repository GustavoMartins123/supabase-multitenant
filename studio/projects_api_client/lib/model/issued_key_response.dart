//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class IssuedKeyResponse {
  /// Returns a new [IssuedKeyResponse] instance.
  IssuedKeyResponse({
    required this.activateAt,
    required this.apiKey,
    required this.apiKeysetVersion,
    required this.expiresAt,
    required this.keyId,
    required this.kind,
    required this.slotId,
    required this.status,
    required this.tokenHint,
  });

  String? activateAt;

  String apiKey;

  int apiKeysetVersion;

  String? expiresAt;

  String keyId;

  String kind;

  String slotId;

  String status;

  String tokenHint;

  @override
  bool operator ==(Object other) => identical(this, other) || other is IssuedKeyResponse &&
    other.activateAt == activateAt &&
    other.apiKey == apiKey &&
    other.apiKeysetVersion == apiKeysetVersion &&
    other.expiresAt == expiresAt &&
    other.keyId == keyId &&
    other.kind == kind &&
    other.slotId == slotId &&
    other.status == status &&
    other.tokenHint == tokenHint;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (activateAt == null ? 0 : activateAt!.hashCode) +
    (apiKey.hashCode) +
    (apiKeysetVersion.hashCode) +
    (expiresAt == null ? 0 : expiresAt!.hashCode) +
    (keyId.hashCode) +
    (kind.hashCode) +
    (slotId.hashCode) +
    (status.hashCode) +
    (tokenHint.hashCode);

  @override
  String toString() => 'IssuedKeyResponse[activateAt=$activateAt, apiKey=$apiKey, apiKeysetVersion=$apiKeysetVersion, expiresAt=$expiresAt, keyId=$keyId, kind=$kind, slotId=$slotId, status=$status, tokenHint=$tokenHint]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.activateAt != null) {
      json[r'activate_at'] = this.activateAt;
    } else {
      json[r'activate_at'] = null;
    }
      json[r'api_key'] = this.apiKey;
      json[r'api_keyset_version'] = this.apiKeysetVersion;
    if (this.expiresAt != null) {
      json[r'expires_at'] = this.expiresAt;
    } else {
      json[r'expires_at'] = null;
    }
      json[r'key_id'] = this.keyId;
      json[r'kind'] = this.kind;
      json[r'slot_id'] = this.slotId;
      json[r'status'] = this.status;
      json[r'token_hint'] = this.tokenHint;
    return json;
  }

  /// Returns a new [IssuedKeyResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static IssuedKeyResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "IssuedKeyResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "IssuedKeyResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return IssuedKeyResponse(
        activateAt: mapValueOfType<String>(json, r'activate_at'),
        apiKey: mapValueOfType<String>(json, r'api_key')!,
        apiKeysetVersion: mapValueOfType<int>(json, r'api_keyset_version')!,
        expiresAt: mapValueOfType<String>(json, r'expires_at'),
        keyId: mapValueOfType<String>(json, r'key_id')!,
        kind: mapValueOfType<String>(json, r'kind')!,
        slotId: mapValueOfType<String>(json, r'slot_id')!,
        status: mapValueOfType<String>(json, r'status')!,
        tokenHint: mapValueOfType<String>(json, r'token_hint')!,
      );
    }
    return null;
  }

  static List<IssuedKeyResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <IssuedKeyResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = IssuedKeyResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, IssuedKeyResponse> mapFromJson(dynamic json) {
    final map = <String, IssuedKeyResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = IssuedKeyResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of IssuedKeyResponse-objects as value to a dart map
  static Map<String, List<IssuedKeyResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<IssuedKeyResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = IssuedKeyResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'activate_at',
    'api_key',
    'api_keyset_version',
    'expires_at',
    'key_id',
    'kind',
    'slot_id',
    'status',
    'token_hint',
  };
}

