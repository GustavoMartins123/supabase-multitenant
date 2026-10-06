//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ReadRowsBody {
  /// Returns a new [ReadRowsBody] instance.
  ReadRowsBody({
    required this.limit,
    required this.table,
  });

  /// Minimum value: 1
  /// Maximum value: 50
  int limit;

  String table;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ReadRowsBody &&
    other.limit == limit &&
    other.table == table;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (limit.hashCode) +
    (table.hashCode);

  @override
  String toString() => 'ReadRowsBody[limit=$limit, table=$table]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'limit'] = this.limit;
      json[r'table'] = this.table;
    return json;
  }

  /// Returns a new [ReadRowsBody] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ReadRowsBody? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return ReadRowsBody(
        limit: mapValueOfType<int>(json, r'limit')!,
        table: mapValueOfType<String>(json, r'table')!,
      );
    }
    return null;
  }

  static List<ReadRowsBody> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ReadRowsBody>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ReadRowsBody.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ReadRowsBody> mapFromJson(dynamic json) {
    final map = <String, ReadRowsBody>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ReadRowsBody.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ReadRowsBody-objects as value to a dart map
  static Map<String, List<ReadRowsBody>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ReadRowsBody>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ReadRowsBody.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'limit',
    'table',
  };
}

