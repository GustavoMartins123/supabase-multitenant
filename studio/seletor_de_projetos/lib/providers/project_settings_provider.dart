import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/project_repository.dart';
import '../models/project_member.dart';
import '../models/all_users.dart';
import '../models/project_docker_status.dart';

final projectMembersProvider = FutureProvider.autoDispose
    .family<List<ProjectMember>, String>((ref, projectRef) async {
  final raw = await ref.watch(projectRepositoryProvider).getMembers(projectRef);
  return raw.map((e) => ProjectMember.fromJson(e)).toList();
});

final availableUsersProvider = FutureProvider.autoDispose
    .family<List<AvailableUserShort>, String>((ref, projectRef) async {
  final raw =
      await ref.watch(projectRepositoryProvider).getAvailableUsers(projectRef);
  return raw.map((e) => AvailableUserShort.fromJson(e)).toList();
});

final projectStatusProvider = FutureProvider.autoDispose
    .family<ProjectDockerStatus, String>((ref, projectRef) async {
  final raw =
      await ref.watch(projectRepositoryProvider).getFullStatus(projectRef);
  return ProjectDockerStatus.fromJson(raw);
});

final projectEnvSettingsProvider = FutureProvider.autoDispose
    .family<ProjectSettingsData, String>((ref, projectRef) async {
  return ref.watch(projectRepositoryProvider).fetchProjectSettings(projectRef);
});
