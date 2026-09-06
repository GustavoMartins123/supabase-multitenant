//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class TelemetryUserItem {
  /// Returns a new [TelemetryUserItem] instance.
  TelemetryUserItem({
    required this.email,
    required this.lastLoginAt,
    required this.phone,
    required this.sessionCount,
    required this.userId,
  });

  String? email;

  String? lastLoginAt;

  String? phone;

  int sessionCount;

  String userId;

  @override
  bool operator ==(Object other) => identical(this, other) || other is TelemetryUserItem &&
    other.email == email &&
    other.lastLoginAt == lastLoginAt &&
    other.phone == phone &&
    other.sessionCount == sessionCount &&
    other.userId == userId;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (email == null ? 0 : email!.hashCode) +
    (lastLoginAt == null ? 0 : lastLoginAt!.hashCode) +
    (phone == null ? 0 : phone!.hashCode) +
    (sessionCount.hashCode) +
    (userId.hashCode);

  @override
  String toString() => 'TelemetryUserItem[email=$email, lastLoginAt=$lastLoginAt, phone=$phone, sessionCount=$sessionCount, userId=$userId]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.email != null) {
      json[r'email'] = this.email;
    } else {
      json[r'email'] = null;
    }
    if (this.lastLoginAt != null) {
      json[r'last_login_at'] = this.lastLoginAt;
    } else {
      json[r'last_login_at'] = null;
    }
    if (this.phone != null) {
      json[r'phone'] = this.phone;
    } else {
      json[r'phone'] = null;
    }
      json[r'session_count'] = this.sessionCount;
      json[r'user_id'] = this.userId;
    return json;
  }

  /// Returns a new [TelemetryUserItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static TelemetryUserItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "TelemetryUserItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "TelemetryUserItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return TelemetryUserItem(
        email: mapValueOfType<String>(json, r'email'),
        lastLoginAt: mapValueOfType<String>(json, r'last_login_at'),
        phone: mapValueOfType<String>(json, r'phone'),
        sessionCount: mapValueOfType<int>(json, r'session_count')!,
        userId: mapValueOfType<String>(json, r'user_id')!,
      );
    }
    return null;
  }

  static List<TelemetryUserItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <TelemetryUserItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = TelemetryUserItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, TelemetryUserItem> mapFromJson(dynamic json) {
    final map = <String, TelemetryUserItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = TelemetryUserItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of TelemetryUserItem-objects as value to a dart map
  static Map<String, List<TelemetryUserItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<TelemetryUserItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = TelemetryUserItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'email',
    'last_login_at',
    'phone',
    'session_count',
    'user_id',
  };
}

