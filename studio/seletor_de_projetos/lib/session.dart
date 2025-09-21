import 'package:flutter/foundation.dart';

class Session {
  static final Session _i = Session._internal();
  Session._internal();
  factory Session() => _i;

  late String myId;
  late String myUsername;
  late String myDisplayName;
  late bool   isSysAdmin;
  final ValueNotifier<Map<String, bool>> _busy = ValueNotifier({});

  bool isBusy(String ref) => _busy.value[ref] ?? false;

  void setBusy(String ref, bool value) {
    final map = Map<String, bool>.from(_busy.value);
    map[ref] = value;
    _busy.value = map;
  }

  ValueListenable<Map<String, bool>> get busyListenable => _busy;
}