import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/project_repository.dart';
import '../models/restore_point.dart';

final restorePointsProvider =
    FutureProvider.autoDispose.family<RestorePointList, String>((ref, name) {
  return ref.watch(projectRepositoryProvider).fetchRestorePoints(name);
});
