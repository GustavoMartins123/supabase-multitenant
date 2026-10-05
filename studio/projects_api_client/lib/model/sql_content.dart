//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SqlContent {
  /// Returns a new [SqlContent] instance.
  SqlContent({
    required this.contentId,
    required this.schemaVersion,
    required this.sql,
  });

  String contentId;

  String schemaVersion;

  String sql;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SqlContent &&
    other.contentId == contentId &&
    other.schemaVersion == schemaVersion &&
    other.sql == sql;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (contentId.hashCode) +
    (schemaVersion.hashCode) +
    (sql.hashCode);

  @override
  String toString() => 'SqlContent[contentId=$contentId, schemaVersion=$schemaVersion, sql=$sql]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'content_id'] = this.contentId;
      json[r'schema_version'] = this.schemaVersion;
      json[r'sql'] = this.sql;
    return json;
  }

  /// Returns a new [SqlContent] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SqlContent? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return SqlContent(
        contentId: mapValueOfType<String>(json, r'content_id')!,
        schemaVersion: mapValueOfType<String>(json, r'schema_version')!,
        sql: mapValueOfType<String>(json, r'sql')!,
      );
    }
    return null;
  }

  static List<SqlContent> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SqlContent>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SqlContent.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SqlContent> mapFromJson(dynamic json) {
    final map = <String, SqlContent>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SqlContent.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SqlContent-objects as value to a dart map
  static Map<String, List<SqlContent>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SqlContent>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SqlContent.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'content_id',
    'schema_version',
    'sql',
  };
}

