import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/api_client.dart';
import '../data/project_repository.dart';
import '../models/job.dart';
import '../session.dart';
import 'project_jobs_provider.dart';

final projectListProvider =
    AsyncNotifierProvider<ProjectListNotifier, List<Map<String, dynamic>>>(
  ProjectListNotifier.new,
);

class ProjectListNotifier extends AsyncNotifier<List<Map<String, dynamic>>> {
  RequestCancellation? _listRequest;

  @override
  Future<List<Map<String, dynamic>>> build() async {
    final cancellation = RequestCancellation();
    _listRequest?.cancel();
    _listRequest = cancellation;
    ref.onDispose(cancellation.cancel);
    return ref.watch(projectRepositoryProvider).fetchProjects(
          cancellation: cancellation,
        );
  }

  Future<void> refresh({bool throwOnError = false}) async {
    _listRequest?.cancel();
    final cancellation = RequestCancellation();
    _listRequest = cancellation;
    state = const AsyncLoading();
    try {
      final projects = await ref.read(projectRepositoryProvider).fetchProjects(
            cancellation: cancellation,
          );
      state = AsyncData(projects);
    } catch (error, stackTrace) {
      state = AsyncError(error, stackTrace);
      if (throwOnError) Error.throwWithStackTrace(error, stackTrace);
    } finally {
      if (identical(_listRequest, cancellation)) _listRequest = null;
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
    required Future<Job> Function() submit,
  }) async {
    try {
      final job = await submit();

      final result = await ref.read(projectJobsProvider.notifier).waitFor(
            job,
            project: project,
            action: action,
            createdBy: Session().myId,
          );
      if (!result.ok) {
        throw ApiException(
          ApiFailureKind.server,
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
