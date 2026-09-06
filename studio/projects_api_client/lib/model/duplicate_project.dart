//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class DuplicateProject {
  /// Returns a new [DuplicateProject] instance.
  DuplicateProject({
    this.copyData = false,
    required this.newName,
    required this.originalName,
    this.resourceProfile,
  });

  bool copyData;

  String newName;

  String originalName;

  DuplicateProjectResourceProfileEnum? resourceProfile;

  @override
  bool operator ==(Object other) => identical(this, other) || other is DuplicateProject &&
    other.copyData == copyData &&
    other.newName == newName &&
    other.originalName == originalName &&
    other.resourceProfile == resourceProfile;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (copyData.hashCode) +
    (newName.hashCode) +
    (originalName.hashCode) +
    (resourceProfile == null ? 0 : resourceProfile!.hashCode);

  @override
  String toString() => 'DuplicateProject[copyData=$copyData, newName=$newName, originalName=$originalName, resourceProfile=$resourceProfile]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'copy_data'] = this.copyData;
      json[r'new_name'] = this.newName;
      json[r'original_name'] = this.originalName;
    if (this.resourceProfile != null) {
      json[r'resource_profile'] = this.resourceProfile;
    } else {
      json[r'resource_profile'] = null;
    }
    return json;
  }

  /// Returns a new [DuplicateProject] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static DuplicateProject? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "DuplicateProject[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "DuplicateProject[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return DuplicateProject(
        copyData: mapValueOfType<bool>(json, r'copy_data') ?? false,
        newName: mapValueOfType<String>(json, r'new_name')!,
        originalName: mapValueOfType<String>(json, r'original_name')!,
        resourceProfile: DuplicateProjectResourceProfileEnum.fromJson(json[r'resource_profile']),
      );
    }
    return null;
  }

  static List<DuplicateProject> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <DuplicateProject>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = DuplicateProject.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, DuplicateProject> mapFromJson(dynamic json) {
    final map = <String, DuplicateProject>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = DuplicateProject.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of DuplicateProject-objects as value to a dart map
  static Map<String, List<DuplicateProject>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<DuplicateProject>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = DuplicateProject.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'new_name',
    'original_name',
  };
}


class DuplicateProjectResourceProfileEnum {
  /// Instantiate a new enum with the provided [value].
  const DuplicateProjectResourceProfileEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const small = DuplicateProjectResourceProfileEnum._(r'small');
  static const medium = DuplicateProjectResourceProfileEnum._(r'medium');
  static const large = DuplicateProjectResourceProfileEnum._(r'large');
  static const custom = DuplicateProjectResourceProfileEnum._(r'custom');

  /// List of all possible values in this [enum][DuplicateProjectResourceProfileEnum].
  static const values = <DuplicateProjectResourceProfileEnum>[
    small,
    medium,
    large,
    custom,
  ];

  static DuplicateProjectResourceProfileEnum? fromJson(dynamic value) => DuplicateProjectResourceProfileEnumTypeTransformer().decode(value);

  static List<DuplicateProjectResourceProfileEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <DuplicateProjectResourceProfileEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = DuplicateProjectResourceProfileEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [DuplicateProjectResourceProfileEnum] to String,
/// and [decode] dynamic data back to [DuplicateProjectResourceProfileEnum].
class DuplicateProjectResourceProfileEnumTypeTransformer {
  factory DuplicateProjectResourceProfileEnumTypeTransformer() => _instance ??= const DuplicateProjectResourceProfileEnumTypeTransformer._();

  const DuplicateProjectResourceProfileEnumTypeTransformer._();

  String encode(DuplicateProjectResourceProfileEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a DuplicateProjectResourceProfileEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  DuplicateProjectResourceProfileEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'small': return DuplicateProjectResourceProfileEnum.small;
        case r'medium': return DuplicateProjectResourceProfileEnum.medium;
        case r'large': return DuplicateProjectResourceProfileEnum.large;
        case r'custom': return DuplicateProjectResourceProfileEnum.custom;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [DuplicateProjectResourceProfileEnumTypeTransformer] instance.
  static DuplicateProjectResourceProfileEnumTypeTransformer? _instance;
}


