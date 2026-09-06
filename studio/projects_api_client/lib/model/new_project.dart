//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class NewProject {
  /// Returns a new [NewProject] instance.
  NewProject({
    required this.name,
    this.resourceProfile = const NewProjectResourceProfileEnum._('medium'),
  });

  String name;

  NewProjectResourceProfileEnum resourceProfile;

  @override
  bool operator ==(Object other) => identical(this, other) || other is NewProject &&
    other.name == name &&
    other.resourceProfile == resourceProfile;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (name.hashCode) +
    (resourceProfile.hashCode);

  @override
  String toString() => 'NewProject[name=$name, resourceProfile=$resourceProfile]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'name'] = this.name;
      json[r'resource_profile'] = this.resourceProfile;
    return json;
  }

  /// Returns a new [NewProject] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static NewProject? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "NewProject[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "NewProject[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return NewProject(
        name: mapValueOfType<String>(json, r'name')!,
        resourceProfile: NewProjectResourceProfileEnum.fromJson(json[r'resource_profile']) ?? const NewProjectResourceProfileEnum._('medium'),
      );
    }
    return null;
  }

  static List<NewProject> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <NewProject>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = NewProject.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, NewProject> mapFromJson(dynamic json) {
    final map = <String, NewProject>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = NewProject.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of NewProject-objects as value to a dart map
  static Map<String, List<NewProject>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<NewProject>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = NewProject.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'name',
  };
}


class NewProjectResourceProfileEnum {
  /// Instantiate a new enum with the provided [value].
  const NewProjectResourceProfileEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const small = NewProjectResourceProfileEnum._(r'small');
  static const medium = NewProjectResourceProfileEnum._(r'medium');
  static const large = NewProjectResourceProfileEnum._(r'large');
  static const custom = NewProjectResourceProfileEnum._(r'custom');

  /// List of all possible values in this [enum][NewProjectResourceProfileEnum].
  static const values = <NewProjectResourceProfileEnum>[
    small,
    medium,
    large,
    custom,
  ];

  static NewProjectResourceProfileEnum? fromJson(dynamic value) => NewProjectResourceProfileEnumTypeTransformer().decode(value);

  static List<NewProjectResourceProfileEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <NewProjectResourceProfileEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = NewProjectResourceProfileEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [NewProjectResourceProfileEnum] to String,
/// and [decode] dynamic data back to [NewProjectResourceProfileEnum].
class NewProjectResourceProfileEnumTypeTransformer {
  factory NewProjectResourceProfileEnumTypeTransformer() => _instance ??= const NewProjectResourceProfileEnumTypeTransformer._();

  const NewProjectResourceProfileEnumTypeTransformer._();

  String encode(NewProjectResourceProfileEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a NewProjectResourceProfileEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  NewProjectResourceProfileEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'small': return NewProjectResourceProfileEnum.small;
        case r'medium': return NewProjectResourceProfileEnum.medium;
        case r'large': return NewProjectResourceProfileEnum.large;
        case r'custom': return NewProjectResourceProfileEnum.custom;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [NewProjectResourceProfileEnumTypeTransformer] instance.
  static NewProjectResourceProfileEnumTypeTransformer? _instance;
}


