//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class FolderBody {
  /// Returns a new [FolderBody] instance.
  FolderBody({
    required this.name,
    this.parentId,
  });

  String name;

  FolderBodyParentIdEnum? parentId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is FolderBody &&
    other.name == name &&
    other.parentId == parentId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (name.hashCode) +
    (parentId == null ? 0 : parentId!.hashCode);

  @override
  String toString() => 'FolderBody[name=$name, parentId=$parentId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'name'] = this.name;
    if (this.parentId != null) {
      json[r'parentId'] = this.parentId;
    } else {
      json[r'parentId'] = null;
    }
    return json;
  }

  /// Returns a new [FolderBody] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static FolderBody? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return FolderBody(
        name: mapValueOfType<String>(json, r'name')!,
        parentId: (json[r'parentId'] == null ? null : throw const FormatException('Invalid null-only field: parentId')),
      );
    }
    return null;
  }

  static List<FolderBody> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <FolderBody>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = FolderBody.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, FolderBody> mapFromJson(dynamic json) {
    final map = <String, FolderBody>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = FolderBody.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of FolderBody-objects as value to a dart map
  static Map<String, List<FolderBody>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<FolderBody>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = FolderBody.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'name',
  };
}


class FolderBodyParentIdEnum {
  /// Instantiate a new enum with the provided [value].
  const FolderBodyParentIdEnum._(this.value);

  /// The underlying value of this enum member.
  final Object value;

  @override
  String toString() => value.toString();

  Object toJson() => value;


  /// List of all possible values in this [enum][FolderBodyParentIdEnum].
  static const values = <FolderBodyParentIdEnum>[
  ];

  static FolderBodyParentIdEnum? fromJson(dynamic value) => FolderBodyParentIdEnumTypeTransformer().decode(value);

  static List<FolderBodyParentIdEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <FolderBodyParentIdEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = FolderBodyParentIdEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [FolderBodyParentIdEnum] to Object,
/// and [decode] dynamic data back to [FolderBodyParentIdEnum].
class FolderBodyParentIdEnumTypeTransformer {
  factory FolderBodyParentIdEnumTypeTransformer() => _instance ??= const FolderBodyParentIdEnumTypeTransformer._();

  const FolderBodyParentIdEnumTypeTransformer._();

  Object encode(FolderBodyParentIdEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a FolderBodyParentIdEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  FolderBodyParentIdEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [FolderBodyParentIdEnumTypeTransformer] instance.
  static FolderBodyParentIdEnumTypeTransformer? _instance;
}


