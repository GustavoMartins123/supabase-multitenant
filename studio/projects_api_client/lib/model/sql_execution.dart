//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SqlExecution {
  /// Returns a new [SqlExecution] instance.
  SqlExecution({
    this.approvalId,
    required this.callId,
    required this.chatId,
    required this.sqlHash,
    required this.tool,
  });

  String? approvalId;

  String callId;

  String chatId;

  String sqlHash;

  SqlExecutionToolEnum tool;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SqlExecution &&
    other.approvalId == approvalId &&
    other.callId == callId &&
    other.chatId == chatId &&
    other.sqlHash == sqlHash &&
    other.tool == tool;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (approvalId == null ? 0 : approvalId!.hashCode) +
    (callId.hashCode) +
    (chatId.hashCode) +
    (sqlHash.hashCode) +
    (tool.hashCode);

  @override
  String toString() => 'SqlExecution[approvalId=$approvalId, callId=$callId, chatId=$chatId, sqlHash=$sqlHash, tool=$tool]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.approvalId != null) {
      json[r'approval_id'] = this.approvalId;
    } else {
      json[r'approval_id'] = null;
    }
      json[r'call_id'] = this.callId;
      json[r'chat_id'] = this.chatId;
      json[r'sql_hash'] = this.sqlHash;
      json[r'tool'] = this.tool;
    return json;
  }

  /// Returns a new [SqlExecution] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SqlExecution? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'approval_id'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return SqlExecution(
        approvalId: mapValueOfType<String>(json, r'approval_id'),
        callId: mapValueOfType<String>(json, r'call_id')!,
        chatId: mapValueOfType<String>(json, r'chat_id')!,
        sqlHash: mapValueOfType<String>(json, r'sql_hash')!,
        tool: SqlExecutionToolEnum.fromJson(json[r'tool'])!,
      );
    }
    return null;
  }

  static List<SqlExecution> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SqlExecution>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SqlExecution.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SqlExecution> mapFromJson(dynamic json) {
    final map = <String, SqlExecution>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SqlExecution.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SqlExecution-objects as value to a dart map
  static Map<String, List<SqlExecution>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SqlExecution>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SqlExecution.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'call_id',
    'chat_id',
    'sql_hash',
    'tool',
  };
}


class SqlExecutionToolEnum {
  /// Instantiate a new enum with the provided [value].
  const SqlExecutionToolEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const executeSql = SqlExecutionToolEnum._(r'execute_sql');
  static const executeDestructiveSql = SqlExecutionToolEnum._(r'execute_destructive_sql');

  /// List of all possible values in this [enum][SqlExecutionToolEnum].
  static const values = <SqlExecutionToolEnum>[
    executeSql,
    executeDestructiveSql,
  ];

  static SqlExecutionToolEnum? fromJson(dynamic value) => SqlExecutionToolEnumTypeTransformer().decode(value);

  static List<SqlExecutionToolEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SqlExecutionToolEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SqlExecutionToolEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [SqlExecutionToolEnum] to String,
/// and [decode] dynamic data back to [SqlExecutionToolEnum].
class SqlExecutionToolEnumTypeTransformer {
  factory SqlExecutionToolEnumTypeTransformer() => _instance ??= const SqlExecutionToolEnumTypeTransformer._();

  const SqlExecutionToolEnumTypeTransformer._();

  String encode(SqlExecutionToolEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a SqlExecutionToolEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  SqlExecutionToolEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'execute_sql': return SqlExecutionToolEnum.executeSql;
        case r'execute_destructive_sql': return SqlExecutionToolEnum.executeDestructiveSql;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [SqlExecutionToolEnumTypeTransformer] instance.
  static SqlExecutionToolEnumTypeTransformer? _instance;
}


