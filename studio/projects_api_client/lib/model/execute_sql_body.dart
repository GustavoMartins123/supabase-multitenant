//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ExecuteSqlBody {
  /// Returns a new [ExecuteSqlBody] instance.
  ExecuteSqlBody({
    required this.execution,
    required this.label,
    required this.permission,
    required this.sql,
  });

  SqlExecution execution;

  String label;

  String permission;

  String sql;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ExecuteSqlBody &&
    other.execution == execution &&
    other.label == label &&
    other.permission == permission &&
    other.sql == sql;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (execution.hashCode) +
    (label.hashCode) +
    (permission.hashCode) +
    (sql.hashCode);

  @override
  String toString() => 'ExecuteSqlBody[execution=$execution, label=$label, permission=$permission, sql=$sql]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'execution'] = this.execution;
      json[r'label'] = this.label;
      json[r'permission'] = this.permission;
      json[r'sql'] = this.sql;
    return json;
  }

  /// Returns a new [ExecuteSqlBody] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ExecuteSqlBody? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return ExecuteSqlBody(
        execution: SqlExecution.fromJson(json[r'execution'])!,
        label: mapValueOfType<String>(json, r'label')!,
        permission: mapValueOfType<String>(json, r'permission')!,
        sql: mapValueOfType<String>(json, r'sql')!,
      );
    }
    return null;
  }

  static List<ExecuteSqlBody> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ExecuteSqlBody>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ExecuteSqlBody.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ExecuteSqlBody> mapFromJson(dynamic json) {
    final map = <String, ExecuteSqlBody>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ExecuteSqlBody.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ExecuteSqlBody-objects as value to a dart map
  static Map<String, List<ExecuteSqlBody>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ExecuteSqlBody>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ExecuteSqlBody.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'execution',
    'label',
    'permission',
    'sql',
  };
}

