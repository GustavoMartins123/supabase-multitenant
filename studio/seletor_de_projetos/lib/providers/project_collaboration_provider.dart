import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/project_repository.dart';
import '../models/project_collaboration.dart';

final projectCollaborationProvider = FutureProvider.autoDispose
    .family<ProjectCollaboration, String>((ref, name) {
  return ref.watch(projectRepositoryProvider).fetchProjectCollaboration(name);
});

final projectRenameHistoryProvider = FutureProvider.autoDispose
    .family<List<ProjectRenameEvent>, String>((ref, name) {
  return ref.watch(projectRepositoryProvider).fetchProjectRenameHistory(name);
});
