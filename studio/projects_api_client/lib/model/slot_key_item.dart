//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SlotKeyItem {
  /// Returns a new [SlotKeyItem] instance.
  SlotKeyItem({
    required this.activateAt,
    required this.activatedAt,
    required this.confirmedAt,
    required this.createdAt,
    required this.currentlyAccepted,
    required this.expiresAt,
    required this.id,
    required this.lastUsedAt,
    required this.replacesKeyId,
    required this.revealedAt,
    required this.revokedAt,
    required this.rotationTrigger,
    required this.status,
    required this.tokenHint,
  });

  String? activateAt;

  String? activatedAt;

  String? confirmedAt;

  String createdAt;

  bool currentlyAccepted;

  String? expiresAt;

  String id;

  String? lastUsedAt;

  String? replacesKeyId;

  String? revealedAt;

  String? revokedAt;

  String? rotationTrigger;

  String status;

  String tokenHint;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SlotKeyItem &&
    other.activateAt == activateAt &&
    other.activatedAt == activatedAt &&
    other.confirmedAt == confirmedAt &&
    other.createdAt == createdAt &&
    other.currentlyAccepted == currentlyAccepted &&
    other.expiresAt == expiresAt &&
    other.id == id &&
    other.lastUsedAt == lastUsedAt &&
    other.replacesKeyId == replacesKeyId &&
    other.revealedAt == revealedAt &&
    other.revokedAt == revokedAt &&
    other.rotationTrigger == rotationTrigger &&
    other.status == status &&
    other.tokenHint == tokenHint;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (activateAt == null ? 0 : activateAt!.hashCode) +
    (activatedAt == null ? 0 : activatedAt!.hashCode) +
    (confirmedAt == null ? 0 : confirmedAt!.hashCode) +
    (createdAt.hashCode) +
    (currentlyAccepted.hashCode) +
    (expiresAt == null ? 0 : expiresAt!.hashCode) +
    (id.hashCode) +
    (lastUsedAt == null ? 0 : lastUsedAt!.hashCode) +
    (replacesKeyId == null ? 0 : replacesKeyId!.hashCode) +
    (revealedAt == null ? 0 : revealedAt!.hashCode) +
    (revokedAt == null ? 0 : revokedAt!.hashCode) +
    (rotationTrigger == null ? 0 : rotationTrigger!.hashCode) +
    (status.hashCode) +
    (tokenHint.hashCode);

  @override
  String toString() => 'SlotKeyItem[activateAt=$activateAt, activatedAt=$activatedAt, confirmedAt=$confirmedAt, createdAt=$createdAt, currentlyAccepted=$currentlyAccepted, expiresAt=$expiresAt, id=$id, lastUsedAt=$lastUsedAt, replacesKeyId=$replacesKeyId, revealedAt=$revealedAt, revokedAt=$revokedAt, rotationTrigger=$rotationTrigger, status=$status, tokenHint=$tokenHint]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.activateAt != null) {
      json[r'activate_at'] = this.activateAt;
    } else {
      json[r'activate_at'] = null;
    }
    if (this.activatedAt != null) {
      json[r'activated_at'] = this.activatedAt;
    } else {
      json[r'activated_at'] = null;
    }
    if (this.confirmedAt != null) {
      json[r'confirmed_at'] = this.confirmedAt;
    } else {
      json[r'confirmed_at'] = null;
    }
      json[r'created_at'] = this.createdAt;
      json[r'currently_accepted'] = this.currentlyAccepted;
    if (this.expiresAt != null) {
      json[r'expires_at'] = this.expiresAt;
    } else {
      json[r'expires_at'] = null;
    }
      json[r'id'] = this.id;
    if (this.lastUsedAt != null) {
      json[r'last_used_at'] = this.lastUsedAt;
    } else {
      json[r'last_used_at'] = null;
    }
    if (this.replacesKeyId != null) {
      json[r'replaces_key_id'] = this.replacesKeyId;
    } else {
      json[r'replaces_key_id'] = null;
    }
    if (this.revealedAt != null) {
      json[r'revealed_at'] = this.revealedAt;
    } else {
      json[r'revealed_at'] = null;
    }
    if (this.revokedAt != null) {
      json[r'revoked_at'] = this.revokedAt;
    } else {
      json[r'revoked_at'] = null;
    }
    if (this.rotationTrigger != null) {
      json[r'rotation_trigger'] = this.rotationTrigger;
    } else {
      json[r'rotation_trigger'] = null;
    }
      json[r'status'] = this.status;
      json[r'token_hint'] = this.tokenHint;
    return json;
  }

  /// Returns a new [SlotKeyItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SlotKeyItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "SlotKeyItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "SlotKeyItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return SlotKeyItem(
        activateAt: mapValueOfType<String>(json, r'activate_at'),
        activatedAt: mapValueOfType<String>(json, r'activated_at'),
        confirmedAt: mapValueOfType<String>(json, r'confirmed_at'),
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        currentlyAccepted: mapValueOfType<bool>(json, r'currently_accepted')!,
        expiresAt: mapValueOfType<String>(json, r'expires_at'),
        id: mapValueOfType<String>(json, r'id')!,
        lastUsedAt: mapValueOfType<String>(json, r'last_used_at'),
        replacesKeyId: mapValueOfType<String>(json, r'replaces_key_id'),
        revealedAt: mapValueOfType<String>(json, r'revealed_at'),
        revokedAt: mapValueOfType<String>(json, r'revoked_at'),
        rotationTrigger: mapValueOfType<String>(json, r'rotation_trigger'),
        status: mapValueOfType<String>(json, r'status')!,
        tokenHint: mapValueOfType<String>(json, r'token_hint')!,
      );
    }
    return null;
  }

  static List<SlotKeyItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SlotKeyItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SlotKeyItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SlotKeyItem> mapFromJson(dynamic json) {
    final map = <String, SlotKeyItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SlotKeyItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SlotKeyItem-objects as value to a dart map
  static Map<String, List<SlotKeyItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SlotKeyItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SlotKeyItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'activate_at',
    'activated_at',
    'confirmed_at',
    'created_at',
    'currently_accepted',
    'expires_at',
    'id',
    'last_used_at',
    'replaces_key_id',
    'revealed_at',
    'revoked_at',
    'rotation_trigger',
    'status',
    'token_hint',
  };
}

