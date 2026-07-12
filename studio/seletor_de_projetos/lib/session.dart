import 'package:flutter/foundation.dart';

import 'models/user_profile.dart';

class Session {
  static final Session _i = Session._internal();
  Session._internal();
  factory Session() => _i;

  late String myId;
  late String myUsername;
  late String myDisplayName;
  late bool isSysAdmin;
  final ValueNotifier<Map<String, bool>> _busy = ValueNotifier({});
  final ValueNotifier<UserProfile?> _profile = ValueNotifier(null);

  bool isBusy(String ref) => _busy.value[ref] ?? false;

  void setBusy(String ref, bool value) {
    final map = Map<String, bool>.from(_busy.value);
    map[ref] = value;
    _busy.value = map;
  }

  void setProfile(UserProfile profile) {
    myId = profile.userId;
    myUsername = profile.username;
    myDisplayName = profile.displayName;
    isSysAdmin = profile.isAdmin;
    _profile.value = profile;
  }

  UserProfile? get profile => _profile.value;
  ValueListenable<UserProfile?> get profileListenable => _profile;
  ValueListenable<Map<String, bool>> get busyListenable => _busy;
}
