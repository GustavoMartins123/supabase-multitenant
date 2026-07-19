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
  final Map<String, Job> _trackedJobs = {};
  final Set<String> _finishedJobIds = {};

  @override
  Future<List<Job>> build() async {
    ref.onDispose(() {
      _disposed = true;
      _pollTimer?.cancel();
    });
    try {
      final jobs = await ref.watch(jobRepositoryProvider).fetchInFlightJobs();
      return _mergeWithTrackedJobs(jobs);
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
      if (!_disposed) state = AsyncData(_mergeWithTrackedJobs(jobs));
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

    _finishedJobIds.remove(tracked.id);
    final previous = _trackedJobs[tracked.id];
    _trackedJobs[tracked.id] =
        previous == null ? tracked : mergeJobSnapshots(previous, tracked);
    state = AsyncData(_mergeWithTrackedJobs(state.value ?? const []));
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
    _trackedJobs.remove(jobId);
    _finishedJobIds.add(jobId);
    final current = [...?state.value]..removeWhere((job) => job.id == jobId);
    state = AsyncData(current);
    unawaited(refresh());
  }

  List<Job> _mergeWithTrackedJobs(Iterable<Job> remoteJobs) {
    final merged = <String, Job>{};
    for (final job in remoteJobs) {
      if (!job.isInFlight || _finishedJobIds.contains(job.id)) continue;
      merged[job.id] = job;
    }
    for (final tracked in _trackedJobs.values) {
      if (!tracked.isInFlight || _finishedJobIds.contains(tracked.id)) {
        continue;
      }
      final remote = merged[tracked.id];
      merged[tracked.id] =
          remote == null ? tracked : mergeJobSnapshots(remote, tracked);
    }

    final jobs = merged.values.toList();
    jobs.sort((a, b) {
      final aDate = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final bDate = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      return aDate.compareTo(bDate);
    });
    return jobs;
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

Job mergeJobSnapshots(Job current, Job incoming) {
  final currentDate = current.updatedAt ?? current.createdAt;
  final incomingDate = incoming.updatedAt ?? incoming.createdAt;
  final incomingIsNewer = switch ((currentDate, incomingDate)) {
    (null, null) => true,
    (null, _) => true,
    (_, null) => false,
    (final currentValue?, final incomingValue?) =>
      !incomingValue.isBefore(currentValue),
  };
  final newest = incomingIsNewer ? incoming : current;
  final fallback = incomingIsNewer ? current : incoming;
  final progressValues =
      [current.progress, incoming.progress].whereType<int>().toList();
  final progress = progressValues.isEmpty
      ? null
      : progressValues.reduce((a, b) => a > b ? a : b);
  final status = current.status == 'running' || incoming.status == 'running'
      ? 'running'
      : newest.status;

  return Job(
    current.id,
    project: newest.project ?? fallback.project,
    projectUuid: newest.projectUuid ?? fallback.projectUuid,
    createdBy: newest.createdBy ?? fallback.createdBy,
    action: newest.action ?? fallback.action,
    status: status,
    message: newest.message ?? fallback.message,
    progress: progress,
    currentStep: newest.currentStep ?? fallback.currentStep,
    totalSteps: newest.totalSteps ?? fallback.totalSteps,
    createdAt: current.createdAt ?? incoming.createdAt,
    updatedAt: incomingDate == null ||
            (currentDate != null && currentDate.isAfter(incomingDate))
        ? current.updatedAt
        : incoming.updatedAt,
  );
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
