import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/project_repository.dart';
import '../services/projectService.dart';

final projectListProvider =
    AsyncNotifierProvider<ProjectListNotifier, List<Map<String, dynamic>>>(
      ProjectListNotifier.new,
    );

class ProjectListNotifier extends AsyncNotifier<List<Map<String, dynamic>>> {
  @override
  Future<List<Map<String, dynamic>>> build() async {
    return ref.watch(projectRepositoryProvider).fetchProjects();
  }

  Future<bool> createProjectAndWait(String name) async {
    final rep = ref.read(projectRepositoryProvider);
    final current = state.value ?? [];

    state = AsyncData([
      ...current,
      {'name': name, 'anon_token': '', 'config_token': '', 'is_loading': true},
    ]);

    final job = await rep.createProject(name);
    if (job == null) {
      _removeLoading(name);
      return false;
    }

    final ok = await ProjectService.waitUntilReady(job.id);
    _removeLoading(name);
    if (ok) {
      ref.invalidateSelf(); // Refresh the full list
    }
    return ok;
  }

  Future<bool> duplicateProjectAndWait(
    String originalName,
    String newName,
    bool copyData,
  ) async {
    final rep = ref.read(projectRepositoryProvider);
    final current = state.value ?? [];

    state = AsyncData([
      ...current,
      {
        'name': newName,
        'anon_token': '',
        'config_token': '',
        'is_loading': true,
      },
    ]);

    final job = await rep.duplicateProject(originalName, newName, copyData);
    if (job == null) {
      _removeLoading(newName);
      return false;
    }

    final ok = await ProjectService.waitUntilReady(job.id);
    _removeLoading(newName);
    if (ok) {
      ref.invalidateSelf(); // Refresh the full list
    }
    return ok;
  }

  void _removeLoading(String name) {
    final current = state.value ?? [];
    state = AsyncData(
      current
          .where((p) => p['name'] != name || p['is_loading'] != true)
          .toList(),
    );
  }

  void removeProjectLocal(String name) {
    final current = state.value ?? [];
    state = AsyncData(current.where((p) => p['name'] != name).toList());
  }

  void updateProjectKey(String projectRef, String newAnonKey) {
    final current = state.value ?? [];
    state = AsyncData(
      current.map((p) {
        if (p['name'] == projectRef) {
          return {...p, 'anon_token': newAnonKey};
        }
        return p;
      }).toList(),
    );
  }
}
