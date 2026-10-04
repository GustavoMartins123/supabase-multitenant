//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ClientConfigurationResponse {
  /// Returns a new [ClientConfigurationResponse] instance.
  ClientConfigurationResponse({
    required this.expiresAt,
    required this.keyId,
    required this.publishableKey,
    required this.supabaseUrl,
  });

  String? expiresAt;

  String keyId;

  String publishableKey;

  String supabaseUrl;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ClientConfigurationResponse &&
    other.expiresAt == expiresAt &&
    other.keyId == keyId &&
    other.publishableKey == publishableKey &&
    other.supabaseUrl == supabaseUrl;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (expiresAt == null ? 0 : expiresAt!.hashCode) +
    (keyId.hashCode) +
    (publishableKey.hashCode) +
    (supabaseUrl.hashCode);

  @override
  String toString() => 'ClientConfigurationResponse[expiresAt=$expiresAt, keyId=$keyId, publishableKey=$publishableKey, supabaseUrl=$supabaseUrl]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.expiresAt != null) {
      json[r'expires_at'] = this.expiresAt;
    } else {
      json[r'expires_at'] = null;
    }
      json[r'key_id'] = this.keyId;
      json[r'publishable_key'] = this.publishableKey;
      json[r'supabase_url'] = this.supabaseUrl;
    return json;
  }

  /// Returns a new [ClientConfigurationResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ClientConfigurationResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'expires_at'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return ClientConfigurationResponse(
        expiresAt: mapValueOfType<String>(json, r'expires_at'),
        keyId: mapValueOfType<String>(json, r'key_id')!,
        publishableKey: mapValueOfType<String>(json, r'publishable_key')!,
        supabaseUrl: mapValueOfType<String>(json, r'supabase_url')!,
      );
    }
    return null;
  }

  static List<ClientConfigurationResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ClientConfigurationResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ClientConfigurationResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ClientConfigurationResponse> mapFromJson(dynamic json) {
    final map = <String, ClientConfigurationResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ClientConfigurationResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ClientConfigurationResponse-objects as value to a dart map
  static Map<String, List<ClientConfigurationResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ClientConfigurationResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ClientConfigurationResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'expires_at',
    'key_id',
    'publishable_key',
    'supabase_url',
  };
}

