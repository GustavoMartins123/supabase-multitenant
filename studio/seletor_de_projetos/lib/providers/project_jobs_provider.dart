import 'dart:async';

import 'package:flutter/widgets.dart';
import '../data/api_client.dart';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/job_repository.dart';
import '../models/job.dart';
import '../services/project_service.dart';
import '../session.dart';

final projectJobsProvider =
    AsyncNotifierProvider<ProjectJobsNotifier, List<Job>>(
  ProjectJobsNotifier.new,
);

final activeProjectJobProvider = Provider.family<Job?, String>((ref, project) {
  final jobs = ref.watch(projectJobsProvider).value ?? const <Job>[];
  return preferredActiveJob(
    jobs.where((job) => job.publicRef == project && job.isInFlight),
  );
});

class ProjectJobsNotifier extends AsyncNotifier<List<Job>> {
  RequestCancellation? _request;
  AppLifecycleListener? _lifecycle;
  bool _disposed = false;
  bool _watching = false;
  bool _initializing = true;
  bool _visible = true;
  bool _failed = false;
  String? _cursor;
  final Map<String, Job> _trackedJobs = {};
  final Map<String, _JobWaiter> _waiters = {};

  @override
  Future<List<Job>> build() async {
    ref.onDispose(() {
      _disposed = true;
      _request?.cancel();
      _lifecycle?.dispose();
      _failWaiters(const ApiException(ApiFailureKind.cancelled,
          'Acompanhamento de jobs encerrado'), StackTrace.current);
    });
    _lifecycle = AppLifecycleListener(onStateChange: (state) {
      _visible = state != AppLifecycleState.hidden &&
          state != AppLifecycleState.paused && state != AppLifecycleState.detached;
      if (!_visible) {
        _request?.cancel();
      } else if (!_failed) {
        _cursor = null;
        _startWatching();
      }
    });
    _request = RequestCancellation();
    final JobSnapshot snapshot;
    try {
      snapshot = await ref.watch(jobRepositoryProvider).watch(cancellation: _request);
    } catch (_) {
      _failed = true;
      rethrow;
    } finally {
      _initializing = false;
    }
    _cursor = snapshot.cursor;
    final jobs = _accept(snapshot.jobs);
    Timer.run(_startWatching);
    return jobs;
  }

  Set<String> get _watchedIds => {
    ..._trackedJobs.keys, ..._waiters.keys,
    for (final job in state.value ?? const <Job>[]) job.id,
  };

  void _startWatching() {
    if (_initializing || _watching || _disposed || !_visible || _failed) return;
    unawaited(_watch());
  }

  Future<void> _watch() async {
    _watching = true;
    try {
      while (!_disposed && _visible && !_failed) {
        final request = _request = RequestCancellation();
        try {
          final snapshot = await ref.read(jobRepositoryProvider).watch(
            cursor: _cursor, watchedIds: _watchedIds, cancellation: request);
          if (_disposed || request.isCancelled) continue;
          _cursor = snapshot.cursor;
          state = AsyncData(_accept(snapshot.jobs));
        } catch (error, stack) {
          if (error is ApiException && error.kind == ApiFailureKind.cancelled) {
            continue;
          }
          _failed = true;
          if (!_disposed) state = AsyncError(error, stack);
          _failWaiters(error, stack);
        }
      }
    } finally {
      _watching = false;
    }
  }

  Future<void> refresh() async {
    if (_disposed) return;
    _failed = false;
    _cursor = null;
    if (!_initializing) _request?.cancel();
    _startWatching();
  }

  void track(Job job, {String? project, String? action, String? createdBy}) {
    if (_disposed) return;
    if (_failed) throw StateError('Job watch unavailable; refresh required');
    final tracked = job.verifyContext(
      project: project, action: action, createdBy: createdBy);
    if (!tracked.isInFlight) return;
    final previous = _trackedJobs[tracked.id];
    _trackedJobs[tracked.id] = previous == null
        ? tracked : mergeJobSnapshots(previous, tracked);
    state = AsyncData(_merge(state.value ?? const []));
    _cursor = null;
    if (!_initializing) _request?.cancel();
    _startWatching();
  }

  List<Job> _accept(List<Job> jobs) {
    for (final job in jobs) {
      final waiter = _waiters[job.id];
      waiter?.update(job);
      if (!job.isInFlight) {
        _trackedJobs.remove(job.id);
        waiter?.complete(job);
        _waiters.remove(job.id);
      } else if (_trackedJobs.containsKey(job.id)) {
        _trackedJobs[job.id] = mergeJobSnapshots(_trackedJobs[job.id]!, job);
      }
    }
    return _merge(jobs.where((job) => job.isInFlight));
  }

  List<Job> _merge(Iterable<Job> jobs) {
    final merged = {for (final job in jobs) job.id: job};
    for (final tracked in _trackedJobs.values) {
      final remote = merged[tracked.id];
      merged[tracked.id] = remote == null
          ? tracked : mergeJobSnapshots(remote, tracked);
    }
    final result = merged.values.toList();
    result.sort((a, b) => (a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0))
        .compareTo(b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0)));
    return result;
  }

  void _failWaiters(Object error, StackTrace stack) {
    for (final waiter in _waiters.values) {
      if (!waiter.completer.isCompleted) waiter.completer.completeError(error, stack);
    }
  }

  Future<JobWaitResult> waitFor(Job job, {
    String? project, String? action, String? createdBy,
    Duration timeout = const Duration(minutes: 30),
    void Function(Map<String, dynamic> data)? onUpdate,
  }) async {
    final verified = job.verifyContext(project: project, action: action,
        createdBy: createdBy ?? Session().myId);
    if (!verified.isInFlight) return _result(verified);
    if (_failed || state.hasError) throw state.error ?? StateError('Job watch unavailable');
    if (_waiters.containsKey(job.id)) throw StateError('Job already being awaited');
    final waiter = _JobWaiter(project, action, createdBy ?? Session().myId, onUpdate);
    _waiters[job.id] = waiter;
    try {
      track(verified);
      final terminal = await waiter.completer.future.timeout(timeout);
      return _result(terminal);
    } finally {
      _waiters.remove(job.id);
    }
  }
}

JobWaitResult _result(Job job) => JobWaitResult(
  ok: job.status == 'done', status: job.status, message: job.message,
  action: job.action, progress: job.progress, currentStep: job.currentStep);

class _JobWaiter {
  _JobWaiter(this.project, this.action, this.createdBy, this.onUpdate);
  final String? project;
  final String? action;
  final String? createdBy;
  final void Function(Map<String, dynamic>)? onUpdate;
  final completer = Completer<Job>();

  void update(Job job) {
    job.verifyContext(project: project, action: action, createdBy: createdBy);
    onUpdate?.call({
      'job_id': job.id, 'project': job.project, 'public_ref': job.publicRef,
      'project_uuid': job.projectUuid, 'tenant_uuid': job.tenantUuid,
      'created_by': job.createdBy, 'action': job.action, 'status': job.status,
      'message': job.message, 'progress': job.progress, 'current_step': job.currentStep,
    });
  }

  void complete(Job job) {
    if (!completer.isCompleted) completer.complete(job);
  }
}

Job mergeJobSnapshots(Job current, Job incoming) {
  for (final pair in [
    (current.id, incoming.id),
    (current.project, incoming.project),
    (current.projectUuid, incoming.projectUuid),
    (current.publicRef, incoming.publicRef),
    (current.tenantUuid, incoming.tenantUuid),
    (current.createdBy, incoming.createdBy),
    (current.action, incoming.action),
  ]) {
    if (pair.$1 != pair.$2) {
      throw const FormatException('Identidade imutavel do job divergente');
    }
  }
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
    project: newest.project,
    projectUuid: newest.projectUuid,
    publicRef: newest.publicRef,
    tenantUuid: newest.tenantUuid,
    createdBy: newest.createdBy,
    action: newest.action,
    status: status,
    message: newest.message,
    progress: progress,
    currentStep: newest.currentStep,
    totalSteps: newest.totalSteps,
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
    final projectUuid = result[i]['project_uuid'] as String;
    indexes[projectUuid] = i;
  }

  for (final job in jobs.where((job) => job.isInFlight)) {
    final project = job.project;
    if (project == null || project.isEmpty) continue;

    final index = indexes[job.projectUuid];
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

    if (job.projectUuid == null || job.publicRef == null) {
      throw const FormatException('Job de criacao sem identidade canonica');
    }
    indexes[job.projectUuid!] = result.length;
    result.add({
      'name': project,
      'display_name': project,
      'project_uuid': job.projectUuid!,
      'public_ref': job.publicRef!,
      'opaque_api_keys_status': 'provisioning',
      'opaque_api_key_slot_count': 0,
      'automatic_key_rotation_enabled': true,
      'automatic_key_rotation_blocked': false,
      'automatic_key_rotation_lead_days': 7,
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
