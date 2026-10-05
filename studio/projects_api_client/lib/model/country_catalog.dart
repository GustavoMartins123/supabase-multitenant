//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class CountryCatalog {
  /// Returns a new [CountryCatalog] instance.
  CountryCatalog({
    this.countries = const [],
    required this.source_,
    required this.version,
  });

  List<CountryItem> countries;

  String source_;

  int version;

  @override
  bool operator ==(Object other) => identical(this, other) || other is CountryCatalog &&
    _deepEquality.equals(other.countries, countries) &&
    other.source_ == source_ &&
    other.version == version;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (countries.hashCode) +
    (source_.hashCode) +
    (version.hashCode);

  @override
  String toString() => 'CountryCatalog[countries=$countries, source_=$source_, version=$version]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'countries'] = this.countries;
      json[r'source'] = this.source_;
      json[r'version'] = this.version;
    return json;
  }

  /// Returns a new [CountryCatalog] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static CountryCatalog? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return CountryCatalog(
        countries: CountryItem.listFromJson(json[r'countries']),
        source_: mapValueOfType<String>(json, r'source')!,
        version: mapValueOfType<int>(json, r'version')!,
      );
    }
    return null;
  }

  static List<CountryCatalog> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <CountryCatalog>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = CountryCatalog.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, CountryCatalog> mapFromJson(dynamic json) {
    final map = <String, CountryCatalog>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = CountryCatalog.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of CountryCatalog-objects as value to a dart map
  static Map<String, List<CountryCatalog>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<CountryCatalog>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = CountryCatalog.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'countries',
    'source',
    'version',
  };
}

