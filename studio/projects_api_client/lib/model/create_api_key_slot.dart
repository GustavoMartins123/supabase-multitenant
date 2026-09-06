//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CreateApiKeySlot {
  /// Returns a new [CreateApiKeySlot] instance.
  CreateApiKeySlot({
    this.allowedServices = const [],
    this.automaticRotationEnabled,
    required this.kind,
    required this.name,
    this.rotationIntervalDays = 90,
  });

  List<String> allowedServices;

  bool? automaticRotationEnabled;

  CreateApiKeySlotKindEnum kind;

  String name;

  /// Minimum value: 1
  /// Maximum value: 3650
  int? rotationIntervalDays;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CreateApiKeySlot &&
    _deepEquality.equals(other.allowedServices, allowedServices) &&
    other.automaticRotationEnabled == automaticRotationEnabled &&
    other.kind == kind &&
    other.name == name &&
    other.rotationIntervalDays == rotationIntervalDays;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (allowedServices.hashCode) +
    (automaticRotationEnabled == null ? 0 : automaticRotationEnabled!.hashCode) +
    (kind.hashCode) +
    (name.hashCode) +
    (rotationIntervalDays == null ? 0 : rotationIntervalDays!.hashCode);

  @override
  String toString() => 'CreateApiKeySlot[allowedServices=$allowedServices, automaticRotationEnabled=$automaticRotationEnabled, kind=$kind, name=$name, rotationIntervalDays=$rotationIntervalDays]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'allowed_services'] = this.allowedServices;
    if (this.automaticRotationEnabled != null) {
      json[r'automatic_rotation_enabled'] = this.automaticRotationEnabled;
    } else {
      json[r'automatic_rotation_enabled'] = null;
    }
      json[r'kind'] = this.kind;
      json[r'name'] = this.name;
    if (this.rotationIntervalDays != null) {
      json[r'rotation_interval_days'] = this.rotationIntervalDays;
    } else {
      json[r'rotation_interval_days'] = null;
    }
    return json;
  }

  /// Returns a new [CreateApiKeySlot] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CreateApiKeySlot? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "CreateApiKeySlot[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "CreateApiKeySlot[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return CreateApiKeySlot(
        allowedServices: json[r'allowed_services'] is Iterable
            ? (json[r'allowed_services'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        automaticRotationEnabled: mapValueOfType<bool>(json, r'automatic_rotation_enabled'),
        kind: CreateApiKeySlotKindEnum.fromJson(json[r'kind'])!,
        name: mapValueOfType<String>(json, r'name')!,
        rotationIntervalDays: mapValueOfType<int>(json, r'rotation_interval_days') ?? 90,
      );
    }
    return null;
  }

  static List<CreateApiKeySlot> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CreateApiKeySlot>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CreateApiKeySlot.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CreateApiKeySlot> mapFromJson(dynamic json) {
    final map = <String, CreateApiKeySlot>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CreateApiKeySlot.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CreateApiKeySlot-objects as value to a dart map
  static Map<String, List<CreateApiKeySlot>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CreateApiKeySlot>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CreateApiKeySlot.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'kind',
    'name',
  };
}


class CreateApiKeySlotKindEnum {
  /// Instantiate a new enum with the provided [value].
  const CreateApiKeySlotKindEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const publishable = CreateApiKeySlotKindEnum._(r'publishable');
  static const secret = CreateApiKeySlotKindEnum._(r'secret');

  /// List of all possible values in this [enum][CreateApiKeySlotKindEnum].
  static const values = <CreateApiKeySlotKindEnum>[
    publishable,
    secret,
  ];

  static CreateApiKeySlotKindEnum? fromJson(dynamic value) => CreateApiKeySlotKindEnumTypeTransformer().decode(value);

  static List<CreateApiKeySlotKindEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CreateApiKeySlotKindEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CreateApiKeySlotKindEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [CreateApiKeySlotKindEnum] to String,
/// and [decode] dynamic data back to [CreateApiKeySlotKindEnum].
class CreateApiKeySlotKindEnumTypeTransformer {
  factory CreateApiKeySlotKindEnumTypeTransformer() => _instance ??= const CreateApiKeySlotKindEnumTypeTransformer._();

  const CreateApiKeySlotKindEnumTypeTransformer._();

  String encode(CreateApiKeySlotKindEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a CreateApiKeySlotKindEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  CreateApiKeySlotKindEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'publishable': return CreateApiKeySlotKindEnum.publishable;
        case r'secret': return CreateApiKeySlotKindEnum.secret;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [CreateApiKeySlotKindEnumTypeTransformer] instance.
  static CreateApiKeySlotKindEnumTypeTransformer? _instance;
}


