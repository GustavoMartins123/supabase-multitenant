class UserProfile {
  const UserProfile({
    required this.userId,
    required this.username,
    required this.email,
    required this.displayName,
    required this.givenName,
    required this.familyName,
    required this.middleName,
    required this.nickname,
    required this.picture,
    required this.website,
    required this.profileUrl,
    required this.gender,
    required this.birthdate,
    required this.zoneinfo,
    required this.locale,
    required this.phoneNumber,
    required this.phoneExtension,
    required this.streetAddress,
    required this.locality,
    required this.region,
    required this.postalCode,
    required this.country,
    required this.groups,
    required this.isActive,
    required this.isAdmin,
    required this.createdAt,
  });

  final String userId;
  final String username;
  final String email;
  final String displayName;
  final String givenName;
  final String familyName;
  final String middleName;
  final String nickname;
  final String picture;
  final String website;
  final String profileUrl;
  final String gender;
  final String birthdate;
  final String zoneinfo;
  final String locale;
  final String phoneNumber;
  final String phoneExtension;
  final String streetAddress;
  final String locality;
  final String region;
  final String postalCode;
  final String country;
  final List<String> groups;
  final bool isActive;
  final bool isAdmin;
  final String createdAt;

  static String _text(Map<String, dynamic> json, String key) =>
      json[key]?.toString() ?? '';

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      userId: _text(json, 'user_id'),
      username: _text(json, 'username'),
      email: _text(json, 'email'),
      displayName: _text(json, 'display_name'),
      givenName: _text(json, 'given_name'),
      familyName: _text(json, 'family_name'),
      middleName: _text(json, 'middle_name'),
      nickname: _text(json, 'nickname'),
      picture: _text(json, 'picture'),
      website: _text(json, 'website'),
      profileUrl: _text(json, 'profile'),
      gender: _text(json, 'gender'),
      birthdate: _text(json, 'birthdate'),
      zoneinfo: _text(json, 'zoneinfo'),
      locale: _text(json, 'locale'),
      phoneNumber: _text(json, 'phone_number'),
      phoneExtension: _text(json, 'phone_extension'),
      streetAddress: _text(json, 'street_address'),
      locality: _text(json, 'locality'),
      region: _text(json, 'region'),
      postalCode: _text(json, 'postal_code'),
      country: _text(json, 'country'),
      groups: (json['groups'] as List<dynamic>? ?? const [])
          .map((value) => value.toString())
          .toList(growable: false),
      isActive: json['is_active'] == true,
      isAdmin: json['is_admin'] == true,
      createdAt: _text(json, 'created_at'),
    );
  }

  String get initials {
    final candidates = [givenName, familyName]
        .where((value) => value.trim().isNotEmpty)
        .toList();
    if (candidates.isNotEmpty) {
      return candidates
          .take(2)
          .map((value) => value.trim().substring(0, 1).toUpperCase())
          .join();
    }
    final value = displayName.trim().isNotEmpty ? displayName : username;
    return value.isEmpty ? '?' : value.substring(0, 1).toUpperCase();
  }
}
