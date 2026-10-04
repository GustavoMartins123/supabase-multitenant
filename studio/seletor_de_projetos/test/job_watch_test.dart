import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/data/job_repository.dart';
import 'package:seletor_de_projetos/models/job.dart';
import 'package:seletor_de_projetos/providers/project_jobs_provider.dart';

const actor = '33333333-3333-4333-8333-333333333333';
const job = Job('00000000-0000-4000-8000-000000000001',
    project: 'select', publicRef: 'abcdefghijklmnopqrst', createdBy: actor,
    action: 'start', status: 'queued');
const terminal = Job('00000000-0000-4000-8000-000000000001',
    project: 'select', publicRef: 'abcdefghijklmnopqrst', createdBy: actor,
    action: 'start', status: 'done', progress: 100);

class Pending {
  Pending(this.ids, this.cancellation, this.cursor);
  final Set<String> ids;
  final RequestCancellation? cancellation;
  final String? cursor;
  final response = Completer<JobSnapshot>();
}

class ControlledWatch extends JobRepository {
  final calls = <Pending>[];
  var active = 0;
  var peak = 0;

  @override
  Future<JobSnapshot> watch({String? cursor, Set<String> watchedIds = const {},
      RequestCancellation? cancellation}) async {
    final pending = Pending(Set.of(watchedIds), cancellation, cursor);
    calls.add(pending);
    active++;
    if (active > peak) peak = active;
    try {
      return await Future.any([
        pending.response.future,
        if (cancellation != null) cancellation.whenCancelled.then<JobSnapshot>((_) {
          throw const ApiException(ApiFailureKind.cancelled, 'Cancelled');
        }),
      ]);
    } finally {
      active--;
    }
  }
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  late ControlledWatch repository;
  late ProviderContainer container;

  setUp(() {
    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    repository = ControlledWatch();
    container = ProviderContainer(overrides: [
      jobRepositoryProvider.overrideWithValue(repository),
    ]);
  });
  tearDown(() {
    container.dispose();
    repository.close();
  });

  Future<void> load() async {
    container.read(projectJobsProvider);
    repository.calls.single.response.complete(JobSnapshot(const [], 'a' * 64));
    await container.read(projectJobsProvider.future);
    await pumpEventQueue(times: 5);
  }

  test('idle keeps one pending request, not queued/running timers', () async {
    await load();
    expect(repository.calls.length, 2);
    await Future<void>.delayed(const Duration(milliseconds: 150));
    expect(repository.calls.length, 2);
    expect(repository.active, 1);
    expect(repository.peak, 1);
  });

  test('waiter uses the same watch and receives terminal state', () async {
    await load();
    final result = container.read(projectJobsProvider.notifier)
        .waitFor(job, createdBy: actor);
    await pumpEventQueue(times: 5);
    expect(repository.calls.last.ids, {job.id});
    expect(repository.peak, 1);
    repository.calls.last.response.complete(JobSnapshot(const [terminal], 'b' * 64));
    expect((await result).ok, isTrue);
    await pumpEventQueue(times: 5);
    expect(container.read(projectJobsProvider).requireValue, isEmpty);
    expect(repository.calls.last.ids, isEmpty);
  });

  test('visible focus changes preserve the cursor and pending watch', () async {
    await load();
    final pending = repository.calls.last;
    for (var i = 0; i < 3; i++) {
      binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    }
    expect(pending.cancellation!.isCancelled, isFalse);
    expect(repository.calls.length, 2);
    pending.response.complete(JobSnapshot(const [], 'a' * 64));
    await pumpEventQueue(times: 5);
    expect(repository.calls.last.cursor, 'a' * 64);
    expect(repository.peak, 1);
  });

  test('hidden tab finishes pending watch then pauses; resume keeps cursor', () async {
    await load();
    final pending = repository.calls.last;
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    expect(pending.cancellation!.isCancelled, isFalse);
    pending.response.complete(JobSnapshot(const [], 'b' * 64));
    await pumpEventQueue(times: 5);
    expect(repository.active, 0);
    final pausedCount = repository.calls.length;
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(repository.calls.length, pausedCount);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await pumpEventQueue(times: 5);
    expect(repository.active, 1);
    expect(repository.calls.length, pausedCount + 1);
    expect(repository.calls.last.cursor, 'b' * 64);
    expect(repository.peak, 1);
  });

  test('quick tab switch does not cancel or duplicate the pending watch', () async {
    await load();
    final pending = repository.calls.last;
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await pumpEventQueue(times: 5);
    expect(pending.cancellation!.isCancelled, isFalse);
    expect(repository.calls.length, 2);
    expect(repository.active, 1);
    expect(repository.peak, 1);
  });

  test('hiding during initial load does not fail initialization', () async {
    container.read(projectJobsProvider);
    final initial = repository.calls.single;
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    expect(initial.cancellation!.isCancelled, isFalse);
    await pumpEventQueue(times: 5);
    initial.response.complete(JobSnapshot(const [], 'a' * 64));
    await container.read(projectJobsProvider.future);
    await pumpEventQueue(times: 5);
    expect(repository.calls.length, 1);
    expect(container.read(projectJobsProvider).hasError, isFalse);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await pumpEventQueue(times: 5);
    expect(repository.calls.last.cursor, 'a' * 64);
    expect(repository.peak, 1);
  });

  test('initially hidden tab loads once and waits until visible', () async {
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    container.read(projectJobsProvider);
    repository.calls.single.response.complete(JobSnapshot(const [], 'a' * 64));
    await container.read(projectJobsProvider.future);
    await pumpEventQueue(times: 5);
    expect(repository.calls.length, 1);
    expect(repository.active, 0);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await pumpEventQueue(times: 5);
    expect(repository.calls.length, 2);
    expect(repository.calls.last.cursor, 'a' * 64);
  });

  test('unexpected cancellation fails closed instead of retrying', () async {
    await load();
    repository.calls.last.response.completeError(
        const ApiException(ApiFailureKind.cancelled, 'Unexpected interruption'));
    await pumpEventQueue(times: 5);
    expect(container.read(projectJobsProvider).hasError, isTrue);
    expect(repository.calls.length, 2);
    expect(repository.active, 0);
  });

  test('authorization failure stops watching and fails the waiter', () async {
    await load();
    final result = container.read(projectJobsProvider.notifier)
        .waitFor(job, createdBy: actor);
    final rejected = expectLater(result, throwsA(isA<ApiException>()));
    await pumpEventQueue(times: 5);
    repository.calls.last.response.completeError(
        const ApiException(ApiFailureKind.forbidden, 'Revoked'));
    await rejected;
    await pumpEventQueue(times: 5);
    final count = repository.calls.length;
    expect(container.read(projectJobsProvider).hasError, isTrue);
    await Future<void>.delayed(const Duration(milliseconds: 100));
    expect(repository.calls.length, count);
    expect(repository.active, 0);
    await container.read(projectJobsProvider.notifier).refresh();
    await pumpEventQueue(times: 5);
    expect(repository.calls.length, count + 1);
  });
}
