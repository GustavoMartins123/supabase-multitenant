//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class RevealItem {
  /// Returns a new [RevealItem] instance.
  RevealItem({
    required this.createdAt,
    required this.keyId,
    required this.keyStatus,
    required this.kind,
    required this.revealedAt,
    required this.slotId,
    required this.slotName,
  });

  String createdAt;

  String keyId;

  String keyStatus;

  String kind;

  String? revealedAt;

  String slotId;

  String slotName;

  @override
  bool operator ==(Object other) => identical(this, other) || other is RevealItem &&
    other.createdAt == createdAt &&
    other.keyId == keyId &&
    other.keyStatus == keyStatus &&
    other.kind == kind &&
    other.revealedAt == revealedAt &&
    other.slotId == slotId &&
    other.slotName == slotName;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (createdAt.hashCode) +
    (keyId.hashCode) +
    (keyStatus.hashCode) +
    (kind.hashCode) +
    (revealedAt == null ? 0 : revealedAt!.hashCode) +
    (slotId.hashCode) +
    (slotName.hashCode);

  @override
  String toString() => 'RevealItem[createdAt=$createdAt, keyId=$keyId, keyStatus=$keyStatus, kind=$kind, revealedAt=$revealedAt, slotId=$slotId, slotName=$slotName]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'created_at'] = this.createdAt;
      json[r'key_id'] = this.keyId;
      json[r'key_status'] = this.keyStatus;
      json[r'kind'] = this.kind;
    if (this.revealedAt != null) {
      json[r'revealed_at'] = this.revealedAt;
    } else {
      json[r'revealed_at'] = null;
    }
      json[r'slot_id'] = this.slotId;
      json[r'slot_name'] = this.slotName;
    return json;
  }

  /// Returns a new [RevealItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static RevealItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "RevealItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "RevealItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return RevealItem(
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        keyId: mapValueOfType<String>(json, r'key_id')!,
        keyStatus: mapValueOfType<String>(json, r'key_status')!,
        kind: mapValueOfType<String>(json, r'kind')!,
        revealedAt: mapValueOfType<String>(json, r'revealed_at'),
        slotId: mapValueOfType<String>(json, r'slot_id')!,
        slotName: mapValueOfType<String>(json, r'slot_name')!,
      );
    }
    return null;
  }

  static List<RevealItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <RevealItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = RevealItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, RevealItem> mapFromJson(dynamic json) {
    final map = <String, RevealItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = RevealItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of RevealItem-objects as value to a dart map
  static Map<String, List<RevealItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<RevealItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = RevealItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'created_at',
    'key_id',
    'key_status',
    'kind',
    'revealed_at',
    'slot_id',
    'slot_name',
  };
}

