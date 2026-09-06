//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class UserSyncResponse {
  /// Returns a new [UserSyncResponse] instance.
  UserSyncResponse({
    required this.email,
    this.groups = const [],
    required this.id,
    required this.isActive,
    required this.pictureUrl,
    this.profile = const {},
    required this.profileUpdatedAt,
    required this.profileVersion,
    required this.username,
  });

  String? email;

  List<String> groups;

  String id;

  bool isActive;

  String? pictureUrl;

  Map<String, Object> profile;

  String? profileUpdatedAt;

  int profileVersion;

  String username;

  @override
  bool operator ==(Object other) => identical(this, other) || other is UserSyncResponse &&
    other.email == email &&
    _deepEquality.equals(other.groups, groups) &&
    other.id == id &&
    other.isActive == isActive &&
    other.pictureUrl == pictureUrl &&
    _deepEquality.equals(other.profile, profile) &&
    other.profileUpdatedAt == profileUpdatedAt &&
    other.profileVersion == profileVersion &&
    other.username == username;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (email == null ? 0 : email!.hashCode) +
    (groups.hashCode) +
    (id.hashCode) +
    (isActive.hashCode) +
    (pictureUrl == null ? 0 : pictureUrl!.hashCode) +
    (profile.hashCode) +
    (profileUpdatedAt == null ? 0 : profileUpdatedAt!.hashCode) +
    (profileVersion.hashCode) +
    (username.hashCode);

  @override
  String toString() => 'UserSyncResponse[email=$email, groups=$groups, id=$id, isActive=$isActive, pictureUrl=$pictureUrl, profile=$profile, profileUpdatedAt=$profileUpdatedAt, profileVersion=$profileVersion, username=$username]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.email != null) {
      json[r'email'] = this.email;
    } else {
      json[r'email'] = null;
    }
      json[r'groups'] = this.groups;
      json[r'id'] = this.id;
      json[r'is_active'] = this.isActive;
    if (this.pictureUrl != null) {
      json[r'picture_url'] = this.pictureUrl;
    } else {
      json[r'picture_url'] = null;
    }
      json[r'profile'] = this.profile;
    if (this.profileUpdatedAt != null) {
      json[r'profile_updated_at'] = this.profileUpdatedAt;
    } else {
      json[r'profile_updated_at'] = null;
    }
      json[r'profile_version'] = this.profileVersion;
      json[r'username'] = this.username;
    return json;
  }

  /// Returns a new [UserSyncResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static UserSyncResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "UserSyncResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "UserSyncResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return UserSyncResponse(
        email: mapValueOfType<String>(json, r'email'),
        groups: json[r'groups'] is Iterable
            ? (json[r'groups'] as Iterable).cast<String>().toList(growable: false)
            : const [],
        id: mapValueOfType<String>(json, r'id')!,
        isActive: mapValueOfType<bool>(json, r'is_active')!,
        pictureUrl: mapValueOfType<String>(json, r'picture_url'),
        profile: mapCastOfType<String, Object>(json, r'profile')!,
        profileUpdatedAt: mapValueOfType<String>(json, r'profile_updated_at'),
        profileVersion: mapValueOfType<int>(json, r'profile_version')!,
        username: mapValueOfType<String>(json, r'username')!,
      );
    }
    return null;
  }

  static List<UserSyncResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <UserSyncResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = UserSyncResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, UserSyncResponse> mapFromJson(dynamic json) {
    final map = <String, UserSyncResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = UserSyncResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of UserSyncResponse-objects as value to a dart map
  static Map<String, List<UserSyncResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<UserSyncResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = UserSyncResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'email',
    'groups',
    'id',
    'is_active',
    'picture_url',
    'profile',
    'profile_updated_at',
    'profile_version',
    'username',
  };
}

