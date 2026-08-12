class OpaqueApiKeyVersion {
  const OpaqueApiKeyVersion({
    required this.id,
    required this.tokenHint,
    required this.status,
    required this.currentlyAccepted,
    required this.createdAt,
    required this.expiresAt,
    required this.rotationTrigger,
    this.activateAt,
    this.activatedAt,
    this.revokedAt,
    this.lastUsedAt,
    this.revealedAt,
    this.confirmedAt,
  });

  final String id;
  final String tokenHint;
  final String status;
  final bool currentlyAccepted;
  final DateTime createdAt;
  final DateTime? activateAt;
  final DateTime expiresAt;
  final DateTime? activatedAt;
  final DateTime? revokedAt;
  final DateTime? lastUsedAt;
  final DateTime? revealedAt;
  final DateTime? confirmedAt;
  final String rotationTrigger;

  factory OpaqueApiKeyVersion.fromJson(Map<String, dynamic> json) {
    return OpaqueApiKeyVersion(
      id: _requiredString(json, 'id'),
      tokenHint: _requiredString(json, 'token_hint'),
      status: _requiredString(json, 'status'),
      currentlyAccepted: _requiredBool(json, 'currently_accepted'),
      createdAt: _requiredDate(json, 'created_at'),
      activateAt: _optionalDate(json, 'activate_at'),
      expiresAt: _requiredDate(json, 'expires_at'),
      activatedAt: _optionalDate(json, 'activated_at'),
      revokedAt: _optionalDate(json, 'revoked_at'),
      lastUsedAt: _optionalDate(json, 'last_used_at'),
      revealedAt: _optionalDate(json, 'revealed_at'),
      confirmedAt: _optionalDate(json, 'confirmed_at'),
      rotationTrigger: _requiredString(json, 'rotation_trigger'),
    );
  }
}

class OpaqueApiKeySlot {
  const OpaqueApiKeySlot({
    required this.id,
    required this.name,
    required this.kind,
    required this.role,
    required this.allowedServices,
    required this.automaticRotationEnabled,
    required this.rotationIntervalDays,
    required this.status,
    required this.createdAt,
    required this.keys,
    this.automaticRotationBlockedAt,
    this.automaticRotationLastError,
  });

  final String id;
  final String name;
  final String kind;
  final String role;
  final List<String> allowedServices;
  final bool automaticRotationEnabled;
  final int rotationIntervalDays;
  final String status;
  final DateTime createdAt;
  final DateTime? automaticRotationBlockedAt;
  final String? automaticRotationLastError;
  final List<OpaqueApiKeyVersion> keys;

  factory OpaqueApiKeySlot.fromJson(Map<String, dynamic> json) {
    final rawServices = json['allowed_services'];
    final rawKeys = json['keys'];
    if (rawServices is! List || rawKeys is! List) {
      throw const FormatException('Slot de API key com listas invalidas');
    }
    return OpaqueApiKeySlot(
      id: _requiredString(json, 'id'),
      name: _requiredString(json, 'name'),
      kind: _requiredString(json, 'kind'),
      role: _requiredString(json, 'role'),
      allowedServices: rawServices.map((item) => item.toString()).toList(),
      automaticRotationEnabled:
          _requiredBool(json, 'automatic_rotation_enabled'),
      rotationIntervalDays: _requiredInt(json, 'rotation_interval_days'),
      status: _requiredString(json, 'status'),
      createdAt: _requiredDate(json, 'created_at'),
      automaticRotationBlockedAt:
          _optionalDate(json, 'automatic_rotation_blocked_at'),
      automaticRotationLastError:
          json['automatic_rotation_last_error']?.toString(),
      keys: rawKeys
          .map(
            (item) => OpaqueApiKeyVersion.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
    );
  }
}

class IssuedOpaqueApiKey {
  const IssuedOpaqueApiKey({
    required this.slotId,
    required this.keyId,
    required this.apiKey,
    required this.tokenHint,
    required this.kind,
    required this.status,
    required this.expiresAt,
    this.activateAt,
  });

  final String slotId;
  final String keyId;
  final String apiKey;
  final String tokenHint;
  final String kind;
  final String status;
  final DateTime? activateAt;
  final DateTime expiresAt;

  factory IssuedOpaqueApiKey.fromJson(Map<String, dynamic> json) {
    return IssuedOpaqueApiKey(
      slotId: _requiredString(json, 'slot_id'),
      keyId: _requiredString(json, 'key_id'),
      apiKey: _requiredString(json, 'api_key'),
      tokenHint: _requiredString(json, 'token_hint'),
      kind: _requiredString(json, 'kind'),
      status: _requiredString(json, 'status'),
      activateAt: _optionalDate(json, 'activate_at'),
      expiresAt: _requiredDate(json, 'expires_at'),
    );
  }
}

class OpaqueApiKeyReveal {
  const OpaqueApiKeyReveal({
    required this.keyId,
    required this.slotId,
    required this.slotName,
    required this.kind,
    required this.createdAt,
    required this.expiresAt,
  });

  final String keyId;
  final String slotId;
  final String slotName;
  final String kind;
  final DateTime createdAt;
  final DateTime expiresAt;

  factory OpaqueApiKeyReveal.fromJson(Map<String, dynamic> json) {
    return OpaqueApiKeyReveal(
      keyId: _requiredString(json, 'key_id'),
      slotId: _requiredString(json, 'slot_id'),
      slotName: _requiredString(json, 'slot_name'),
      kind: _requiredString(json, 'kind'),
      createdAt: _requiredDate(json, 'created_at'),
      expiresAt: _requiredDate(json, 'expires_at'),
    );
  }
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.isEmpty) {
    throw FormatException('Campo obrigatorio invalido: $key');
  }
  return value;
}

bool _requiredBool(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! bool) throw FormatException('Campo booleano invalido: $key');
  return value;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! int) throw FormatException('Campo inteiro invalido: $key');
  return value;
}

DateTime _requiredDate(Map<String, dynamic> json, String key) {
  final value = _requiredString(json, key);
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('Data invalida: $key');
  return parsed;
}

DateTime? _optionalDate(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value == null) return null;
  if (value is! String) throw FormatException('Data invalida: $key');
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('Data invalida: $key');
  return parsed;
}
