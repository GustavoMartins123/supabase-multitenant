import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/user_models.dart';
import '../data/project_repository.dart';

final adminUsersProvider =
    AsyncNotifierProvider<AdminUsersNotifier, UserListResponse>(
      () => AdminUsersNotifier(),
    );

class AdminUsersNotifier extends AsyncNotifier<UserListResponse> {
  @override
  Future<UserListResponse> build() async {
    return ref.read(projectRepositoryProvider).fetchAdminUsers();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(
      () => ref.read(projectRepositoryProvider).fetchAdminUsers(),
    );
  }

  Future<void> toggleUserStatus(String userId, bool isCurrentlyActive) async {
    try {
      await ref
          .read(projectRepositoryProvider)
          .toggleUserStatus(userId, isCurrentlyActive);
      // Wait for it to apply, then refresh the list
      await refresh();
    } catch (e) {
      rethrow;
    }
  }
}
