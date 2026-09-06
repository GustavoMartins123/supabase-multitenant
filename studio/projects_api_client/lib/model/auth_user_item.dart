//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class AuthUserItem {
  /// Returns a new [AuthUserItem] instance.
  AuthUserItem({
    this.createdAt,
    this.email,
    this.emailConfirmedAt,
    required this.id,
    this.isSsoUser,
    this.lastSignInAt,
    this.phone,
    this.rawUserMetaData = const {},
  });

  String? createdAt;

  String? email;

  String? emailConfirmedAt;

  String id;

  bool? isSsoUser;

  String? lastSignInAt;

  String? phone;

  Map<String, Object>? rawUserMetaData;

  @override
  bool operator ==(Object other) => identical(this, other) || other is AuthUserItem &&
    other.createdAt == createdAt &&
    other.email == email &&
    other.emailConfirmedAt == emailConfirmedAt &&
    other.id == id &&
    other.isSsoUser == isSsoUser &&
    other.lastSignInAt == lastSignInAt &&
    other.phone == phone &&
    _deepEquality.equals(other.rawUserMetaData, rawUserMetaData);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (createdAt == null ? 0 : createdAt!.hashCode) +
    (email == null ? 0 : email!.hashCode) +
    (emailConfirmedAt == null ? 0 : emailConfirmedAt!.hashCode) +
    (id.hashCode) +
    (isSsoUser == null ? 0 : isSsoUser!.hashCode) +
    (lastSignInAt == null ? 0 : lastSignInAt!.hashCode) +
    (phone == null ? 0 : phone!.hashCode) +
    (rawUserMetaData == null ? 0 : rawUserMetaData!.hashCode);

  @override
  String toString() => 'AuthUserItem[createdAt=$createdAt, email=$email, emailConfirmedAt=$emailConfirmedAt, id=$id, isSsoUser=$isSsoUser, lastSignInAt=$lastSignInAt, phone=$phone, rawUserMetaData=$rawUserMetaData]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.createdAt != null) {
      json[r'created_at'] = this.createdAt;
    } else {
      json[r'created_at'] = null;
    }
    if (this.email != null) {
      json[r'email'] = this.email;
    } else {
      json[r'email'] = null;
    }
    if (this.emailConfirmedAt != null) {
      json[r'email_confirmed_at'] = this.emailConfirmedAt;
    } else {
      json[r'email_confirmed_at'] = null;
    }
      json[r'id'] = this.id;
    if (this.isSsoUser != null) {
      json[r'is_sso_user'] = this.isSsoUser;
    } else {
      json[r'is_sso_user'] = null;
    }
    if (this.lastSignInAt != null) {
      json[r'last_sign_in_at'] = this.lastSignInAt;
    } else {
      json[r'last_sign_in_at'] = null;
    }
    if (this.phone != null) {
      json[r'phone'] = this.phone;
    } else {
      json[r'phone'] = null;
    }
    if (this.rawUserMetaData != null) {
      json[r'raw_user_meta_data'] = this.rawUserMetaData;
    } else {
      json[r'raw_user_meta_data'] = null;
    }
    return json;
  }

  /// Returns a new [AuthUserItem] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static AuthUserItem? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "AuthUserItem[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "AuthUserItem[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return AuthUserItem(
        createdAt: mapValueOfType<String>(json, r'created_at'),
        email: mapValueOfType<String>(json, r'email'),
        emailConfirmedAt: mapValueOfType<String>(json, r'email_confirmed_at'),
        id: mapValueOfType<String>(json, r'id')!,
        isSsoUser: mapValueOfType<bool>(json, r'is_sso_user'),
        lastSignInAt: mapValueOfType<String>(json, r'last_sign_in_at'),
        phone: mapValueOfType<String>(json, r'phone'),
        rawUserMetaData: mapCastOfType<String, Object>(json, r'raw_user_meta_data') ?? const {},
      );
    }
    return null;
  }

  static List<AuthUserItem> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <AuthUserItem>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = AuthUserItem.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, AuthUserItem> mapFromJson(dynamic json) {
    final map = <String, AuthUserItem>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = AuthUserItem.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of AuthUserItem-objects as value to a dart map
  static Map<String, List<AuthUserItem>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<AuthUserItem>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = AuthUserItem.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'id',
  };
}

