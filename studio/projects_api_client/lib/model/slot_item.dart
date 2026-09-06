//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SlotItem {
  /// Returns a new [SlotItem] instance.
  SlotItem({
    this.allowedServices = const [],
    required this.automaticRotationBlockedAt,
    required this.automaticRotationEnabled,
    required this.automaticRotationLastError,
    required this.createdAt,
    required this.id,
    this.keys = const [],
    required this.kind,
    required this.name,
    required this.role,
    required this.rotationIntervalDays,
    required this.status,
  });

  List<String> allowedServices;

  String? automaticRotationBlockedAt;

  bool automaticRotationEnabled;

  String? automaticRotationLastError;

  String createdAt;

  String id;

  List<SlotKeyItem> keys;

  String kind;

  String name;

  String role;

  int? rotationIntervalDays;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SlotItem &&
    _deepEquality.equals(other.allowedServices, allowedServices) &&
    other.automaticRotationBlockedAt == automaticRotationBlockedAt &&
    other.automaticRotationEnabled == automaticRotationEnabled &&
    other.automaticRotationLastError == automaticRotationLastError &&
    other.createdAt == createdAt &&
    other.id == id &&
    _deepEquality.equals(other.keys, keys) &&
    other.kind == kind &&
    other.name == name &&
    other.role == role &&
    other.rotationIntervalDays == rotationIntervalDays &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (allowedServices.hashCode) +
    (automaticRotationBlockedAt == null ? 0 : automaticRotationBlockedAt!.hashCode) +
    (automaticRotationEnabled.hashCode) +
    (automaticRotationLastError == null ? 0 : automaticRotationLastError!.hashCode) +
    (createdAt.hashCode) +
    (id.hashCode) +
    (keys.hashCode) +
    (kind.hashCode) +
    (name.hashCode) +
    (role.hashCode) +
    (rotationIntervalDays == null ? 0 : rotationIntervalDays!.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'SlotItem[allowedServices=$allowedServices, automaticRotationBlockedAt=$automaticRotationBlockedAt, automaticRotationEnabled=$automaticRotationEnabled, automaticRotationLastError=$automaticRotationLastError, createdAt=$createdAt, id=$id, keys=$keys, kind=$kind, name=$name, role=$role, rotationIntervalDays=$rotationIntervalDays, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'allowed_services'] = this.allowedServices;
    if (this.automaticRotationBlockedAt != null) {
      json[r'automatic_rotation_blocked_at'] = this.automaticRotationBlockedAt;
    } else {
      json[r'automatic_rotation_blocked_at'] = null;
    }
      json[r'automatic_rotation_enabled'] = this.automaticRotationEnabled;
    if (this.automaticRotationLastError != null) {
      json[r'automatic_rotation_last_error'] = this.automaticRotationLastError;
    } else {
      json[r'automatic_rotation_last_error'] = null;
    }
      json[r'created_at'] = this.createdAt;
      json[r'id'] = this.id;
      json[r'keys'] = this.keys;
      json[r'kind'] = this.kind;
      json[r'name'] = this.name;
      json[r'role'] = this.role;
    if (this.rotationIntervalDays != null) {
      json[r'rotation_interval_days'] = this.rotationIntervalDays;
    } else {
      json[r'rotation_interval_days'] = null;
    }
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [SlotItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SlotItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "SlotItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "SlotItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return SlotItem(
        allowedServices: json[r'allowed_services'] is Iterable
            ? (json[r'allowed_services'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        automaticRotationBlockedAt: mapValueOfType<String>(json, r'automatic_rotation_blocked_at'),
        automaticRotationEnabled: mapValueOfType<bool>(json, r'automatic_rotation_enabled')!,
        automaticRotationLastError: mapValueOfType<String>(json, r'automatic_rotation_last_error'),
        createdAt: mapValueOfType<String>(json, r'created_at')!,
        id: mapValueOfType<String>(json, r'id')!,
        keys: SlotKeyItem.listFromJson(json[r'keys']),
        kind: mapValueOfType<String>(json, r'kind')!,
        name: mapValueOfType<String>(json, r'name')!,
        role: mapValueOfType<String>(json, r'role')!,
        rotationIntervalDays: mapValueOfType<int>(json, r'rotation_interval_days'),
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<SlotItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SlotItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SlotItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SlotItem> mapFromJson(dynamic json) {
    final map = <String, SlotItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SlotItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SlotItem-objects as value to a dart map
  static Map<String, List<SlotItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SlotItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SlotItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'allowed_services',
    'automatic_rotation_blocked_at',
    'automatic_rotation_enabled',
    'automatic_rotation_last_error',
    'created_at',
    'id',
    'keys',
    'kind',
    'name',
    'role',
    'rotation_interval_days',
    'status',
  };
}

