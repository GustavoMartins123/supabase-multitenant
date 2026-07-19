import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/job_repository.dart';
import '../models/job.dart';
import '../services/projectService.dart';
import '../session.dart';

final projectJobsProvider =
    AsyncNotifierProvider<ProjectJobsNotifier, List<Job>>(
  ProjectJobsNotifier.new,
);

final activeProjectJobProvider = Provider.family<Job?, String>((ref, project) {
  final jobs = ref.watch(projectJobsProvider).value ?? const <Job>[];
  return preferredActiveJob(
    jobs.where((job) => job.project == project && job.isInFlight),
  );
});

class ProjectJobsNotifier extends AsyncNotifier<List<Job>> {
  static const pollInterval = Duration(seconds: 3);

  Timer? _pollTimer;
  bool _refreshing = false;
  bool _disposed = false;

  @override
  Future<List<Job>> build() async {
    ref.onDispose(() {
      _disposed = true;
      _pollTimer?.cancel();
    });
    try {
      return await ref.watch(jobRepositoryProvider).fetchInFlightJobs();
    } finally {
      _startPolling();
    }
  }

  void _startPolling() {
    if (_disposed) return;
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(
      pollInterval,
      (_) => unawaited(refresh()),
    );
  }

  Future<void> refresh() async {
    if (_refreshing || _disposed) return;
    _refreshing = true;
    try {
      final jobs = await ref.read(jobRepositoryProvider).fetchInFlightJobs();
      if (!_disposed) state = AsyncData(jobs);
    } catch (error, stackTrace) {
      if (!_disposed && !state.hasValue) {
        state = AsyncError(error, stackTrace);
      }
    } finally {
      _refreshing = false;
    }
  }

  void track(
    Job job, {
    String? project,
    String? action,
    String? createdBy,
  }) {
    if (_disposed) return;
    final tracked = job.withFallback(
      project: project,
      action: action,
      createdBy: createdBy,
    );
    if (!tracked.isInFlight) return;

    final current = [...?state.value];
    final index = current.indexWhere((item) => item.id == tracked.id);
    if (index == -1) {
      current.add(tracked);
    } else {
      current[index] = tracked;
    }
    state = AsyncData(current);
  }

  void updateFromJson(
    Map<String, dynamic> json, {
    String? project,
    String? action,
    String? createdBy,
  }) {
    final job = Job.fromJson(json).withFallback(
      project: project,
      action: action,
      createdBy: createdBy,
    );
    if (job.isInFlight) {
      track(job);
    } else {
      finish(job.id);
    }
  }

  void finish(String jobId) {
    if (_disposed) return;
    final current = [...?state.value]..removeWhere((job) => job.id == jobId);
    state = AsyncData(current);
    unawaited(refresh());
  }

  Future<JobWaitResult> waitFor(
    Job job, {
    String? project,
    String? action,
    String? createdBy,
    Duration every = const Duration(seconds: 3),
    int max = 600,
    void Function(Map<String, dynamic> data)? onUpdate,
  }) async {
    final effectiveCreatedBy = createdBy ?? Session().myId;
    track(
      job,
      project: project,
      action: action,
      createdBy: effectiveCreatedBy,
    );
    try {
      return await ProjectService.waitForJob(
        job.id,
        every: every,
        max: max,
        onUpdate: (data) {
          updateFromJson(
            data,
            project: project,
            action: action,
            createdBy: effectiveCreatedBy,
          );
          onUpdate?.call(data);
        },
      );
    } finally {
      finish(job.id);
    }
  }
}

List<Map<String, dynamic>> mergeProjectsWithJobs({
  required List<Map<String, dynamic>> projects,
  required List<Job> jobs,
  required String currentUserId,
}) {
  final result = projects.map(Map<String, dynamic>.from).toList();
  final indexes = <String, int>{};
  for (var i = 0; i < result.length; i++) {
    final name = result[i]['name']?.toString();
    if (name != null) indexes[name] = i;
  }

  for (final job in jobs.where((job) => job.isInFlight)) {
    final project = job.project;
    if (project == null || project.isEmpty) continue;

    final index = indexes[project];
    if (index != null) {
      final currentJob = result[index]['active_job'] as Job?;
      result[index]['active_job'] = preferredActiveJob([
        if (currentJob != null) currentJob,
        job,
      ]);
      continue;
    }

    final createsVisibleProject =
        (job.action == 'create' || job.action == 'duplicate') &&
            job.createdBy == currentUserId;
    if (!createsVisibleProject) continue;

    indexes[project] = result.length;
    result.add({
      'name': project,
      'anon_token': '',
      'file_size_limit': '',
      'storage_limit_token': '',
      'is_loading': true,
      'active_job': job,
    });
  }

  return result;
}

Job? preferredActiveJob(Iterable<Job> jobs) {
  final active = jobs.where((job) => job.isInFlight).toList();
  if (active.isEmpty) return null;

  final running = active.where((job) => job.status == 'running').toList();
  final candidates = running.isNotEmpty ? running : active;
  candidates.sort((a, b) {
    final aDate = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final bDate = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    return running.isNotEmpty ? bDate.compareTo(aDate) : aDate.compareTo(bDate);
  });
  return candidates.first;
}
