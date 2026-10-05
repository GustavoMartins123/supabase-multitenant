//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class PrivilegeExecution {
  /// Returns a new [PrivilegeExecution] instance.
  PrivilegeExecution({
    required this.approvalId,
    required this.callId,
    required this.chatId,
    required this.sqlHash,
    required this.tool,
  });

  String approvalId;

  String callId;

  String chatId;

  String sqlHash;

  String tool;

  @override
  bool operator ==(Object other) => identical(this, other) || other is PrivilegeExecution &&
    other.approvalId == approvalId &&
    other.callId == callId &&
    other.chatId == chatId &&
    other.sqlHash == sqlHash &&
    other.tool == tool;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (approvalId.hashCode) +
    (callId.hashCode) +
    (chatId.hashCode) +
    (sqlHash.hashCode) +
    (tool.hashCode);

  @override
  String toString() => 'PrivilegeExecution[approvalId=$approvalId, callId=$callId, chatId=$chatId, sqlHash=$sqlHash, tool=$tool]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'approval_id'] = this.approvalId;
      json[r'call_id'] = this.callId;
      json[r'chat_id'] = this.chatId;
      json[r'sql_hash'] = this.sqlHash;
      json[r'tool'] = this.tool;
    return json;
  }

  /// Returns a new [PrivilegeExecution] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static PrivilegeExecution? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return PrivilegeExecution(
        approvalId: mapValueOfType<String>(json, r'approval_id')!,
        callId: mapValueOfType<String>(json, r'call_id')!,
        chatId: mapValueOfType<String>(json, r'chat_id')!,
        sqlHash: mapValueOfType<String>(json, r'sql_hash')!,
        tool: mapValueOfType<String>(json, r'tool')!,
      );
    }
    return null;
  }

  static List<PrivilegeExecution> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PrivilegeExecution>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PrivilegeExecution.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, PrivilegeExecution> mapFromJson(dynamic json) {
    final map = <String, PrivilegeExecution>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = PrivilegeExecution.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of PrivilegeExecution-objects as value to a dart map
  static Map<String, List<PrivilegeExecution>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<PrivilegeExecution>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = PrivilegeExecution.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'approval_id',
    'call_id',
    'chat_id',
    'sql_hash',
    'tool',
  };
}

