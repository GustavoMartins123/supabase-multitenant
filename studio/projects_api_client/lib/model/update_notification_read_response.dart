//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class UpdateNotificationReadResponse {
  /// Returns a new [UpdateNotificationReadResponse] instance.
  UpdateNotificationReadResponse({
    required this.id,
    required this.read,
    required this.readAt,
  });

  String id;

  bool read;

  String? readAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is UpdateNotificationReadResponse &&
    other.id == id &&
    other.read == read &&
    other.readAt == readAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (id.hashCode) +
    (read.hashCode) +
    (readAt == null ? 0 : readAt!.hashCode);

  @override
  String toString() => 'UpdateNotificationReadResponse[id=$id, read=$read, readAt=$readAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'id'] = this.id;
      json[r'read'] = this.read;
    if (this.readAt != null) {
      json[r'read_at'] = this.readAt;
    } else {
      json[r'read_at'] = null;
    }
    return json;
  }

  /// Returns a new [UpdateNotificationReadResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static UpdateNotificationReadResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'read_at'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return UpdateNotificationReadResponse(
        id: mapValueOfType<String>(json, r'id')!,
        read: mapValueOfType<bool>(json, r'read')!,
        readAt: mapValueOfType<String>(json, r'read_at'),
      );
    }
    return null;
  }

  static List<UpdateNotificationReadResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <UpdateNotificationReadResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = UpdateNotificationReadResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, UpdateNotificationReadResponse> mapFromJson(dynamic json) {
    final map = <String, UpdateNotificationReadResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = UpdateNotificationReadResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of UpdateNotificationReadResponse-objects as value to a dart map
  static Map<String, List<UpdateNotificationReadResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<UpdateNotificationReadResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = UpdateNotificationReadResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'id',
    'read',
    'read_at',
  };
}

