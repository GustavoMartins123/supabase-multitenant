//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AuthUsersResponse {
  /// Returns a new [AuthUsersResponse] instance.
  AuthUsersResponse({
    this.total = 0,
    this.users = const [],
  });

  int total;

  List<AuthUserItem> users;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AuthUsersResponse &&
    other.total == total &&
    _deepEquality.equals(other.users, users);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (total.hashCode) +
    (users.hashCode);

  @override
  String toString() => 'AuthUsersResponse[total=$total, users=$users]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'total'] = this.total;
      json[r'users'] = this.users;
    return json;
  }

  /// Returns a new [AuthUsersResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AuthUsersResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "AuthUsersResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "AuthUsersResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return AuthUsersResponse(
        total: mapValueOfType<int>(json, r'total') ?? 0,
        users: AuthUserItem.listFromJson(json[r'users']),
      );
    }
    return null;
  }

  static List<AuthUsersResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AuthUsersResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AuthUsersResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AuthUsersResponse> mapFromJson(dynamic json) {
    final map = <String, AuthUsersResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AuthUsersResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AuthUsersResponse-objects as value to a dart map
  static Map<String, List<AuthUsersResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AuthUsersResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AuthUsersResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
  };
}

