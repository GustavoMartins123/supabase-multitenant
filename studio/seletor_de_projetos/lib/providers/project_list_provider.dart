import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/project_repository.dart';
import '../models/job.dart';
import '../session.dart';
import 'project_jobs_provider.dart';

final projectListProvider =
    AsyncNotifierProvider<ProjectListNotifier, List<Map<String, dynamic>>>(
  ProjectListNotifier.new,
);

class ProjectListNotifier extends AsyncNotifier<List<Map<String, dynamic>>> {
  @override
  Future<List<Map<String, dynamic>>> build() async {
    return ref.watch(projectRepositoryProvider).fetchProjects();
  }

  Future<List<Map<String, dynamic>>> refresh(
      {bool throwOnError = false}) async {
    final previous = state.value;
    if (previous == null) state = const AsyncLoading();
    try {
      final projects =
          await ref.read(projectRepositoryProvider).fetchProjects();
      state = AsyncData(projects);
      return projects;
    } catch (error, stackTrace) {
      if (previous == null) {
        state = AsyncError(error, stackTrace);
        if (throwOnError) Error.throwWithStackTrace(error, stackTrace);
        return const [];
      }
      state = AsyncData(previous);
      if (throwOnError) Error.throwWithStackTrace(error, stackTrace);
      return previous;
    }
  }

  Future<bool> createProjectAndWait(String name) async {
    final rep = ref.read(projectRepositoryProvider);
    final current = state.value ?? [];

    state = AsyncData([
      ...current,
      {
        'name': name,
        'anon_token': '',
        'file_size_limit': '',
        'storage_limit_token': '',
        'is_loading': true,
      },
    ]);

    return _submitAndTrack(
      project: name,
      action: 'create',
      submit: () => rep.createProject(name),
    );
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
        'file_size_limit': '',
        'storage_limit_token': '',
        'is_loading': true,
      },
    ]);

    return _submitAndTrack(
      project: newName,
      action: 'duplicate',
      submit: () => rep.duplicateProject(originalName, newName, copyData),
    );
  }

  Future<bool> _submitAndTrack({
    required String project,
    required String action,
    required Future<Job?> Function() submit,
  }) async {
    Job? job;
    try {
      job = await submit();
      if (job == null) {
        throw Exception('A API não retornou o job da operação.');
      }

      final result = await ref.read(projectJobsProvider.notifier).waitFor(
            job,
            project: project,
            action: action,
            createdBy: Session().myId,
          );
      if (!result.ok) {
        throw Exception(
          result.message ?? 'A operação falhou sem diagnóstico do servidor.',
        );
      }
      return true;
    } finally {
      _removeLoading(project);
      await refresh();
    }
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
