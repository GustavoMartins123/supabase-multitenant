//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CountryItem {
  /// Returns a new [CountryItem] instance.
  CountryItem({
    required this.code,
    required this.name,
    required this.nameEn,
  });

  String code;

  String name;

  String nameEn;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CountryItem &&
    other.code == code &&
    other.name == name &&
    other.nameEn == nameEn;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (code.hashCode) +
    (name.hashCode) +
    (nameEn.hashCode);

  @override
  String toString() => 'CountryItem[code=$code, name=$name, nameEn=$nameEn]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'code'] = this.code;
      json[r'name'] = this.name;
      json[r'name_en'] = this.nameEn;
    return json;
  }

  /// Returns a new [CountryItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CountryItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return CountryItem(
        code: mapValueOfType<String>(json, r'code')!,
        name: mapValueOfType<String>(json, r'name')!,
        nameEn: mapValueOfType<String>(json, r'name_en')!,
      );
    }
    return null;
  }

  static List<CountryItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CountryItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CountryItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CountryItem> mapFromJson(dynamic json) {
    final map = <String, CountryItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CountryItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CountryItem-objects as value to a dart map
  static Map<String, List<CountryItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CountryItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CountryItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'code',
    'name',
    'name_en',
  };
}

