import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/job_repository.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/models/job.dart';
import 'package:seletor_de_projetos/providers/project_jobs_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('Job', () {
    test('parses the durable job payload returned by the API', () {
      final job = Job.fromJson({
        'job_id': '00000000-0000-4000-8000-000000000001',
        'project': 'meu_projeto',
        'project_uuid': '11111111-1111-4111-8111-111111111111',
        'public_ref': 'aaaaaaaaaaaaaaaaaaaa',
        'tenant_uuid': '22222222-2222-4222-8222-222222222222',
        'created_by': '33333333-3333-4333-8333-333333333333',
        'action': 'create',
        'status': 'running',
        'message': 'Provisionando infraestrutura do projeto...',
        'progress': 10.0,
        'current_step': 'provision_infrastructure',
        'total_steps': 3,
        'created_at': '2026-07-19T03:08:48.079739+00:00',
      });

      expect(job.id, '00000000-0000-4000-8000-000000000001');
      expect(job.project, 'meu_projeto');
      expect(job.action, 'create');
      expect(job.tenantUuid, '22222222-2222-4222-8222-222222222222');
      expect(job.progress, 10);
      expect(job.currentStep, 'provision_infrastructure');
      expect(job.isInFlight, isTrue);
      expect(job.createdAt, isNotNull);
    });

    test('rename polling uses only the original public reference', () {
      const completedRename = Job(
        'job-rename',
        project: 'projeto_tecnico',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        action: 'rename',
        status: 'done',
      );
      expect(completedRename.verifyContext(project: 'aaaaaaaaaaaaaaaaaaaa'),
          same(completedRename));
      for (final ref in [
        'bbbbbbbbbbbbbbbbbbbb',
        'projeto_tecnico',
        '11111111-1111-4111-8111-111111111111'
      ]) {
        expect(() => completedRename.verifyContext(project: ref),
            throwsFormatException);
      }
    });
  });

  group('JobRepository', () {
    test('one watch returns both queued and running jobs', () async {
      var requests = 0;
      final repository = JobRepository(client: MockClient((request) async {
        requests++;
        expect(request.url.path, '/api/jobs/watch');
        expect(request.url.queryParameters.containsKey('status'), isFalse);
        return http.Response(jsonEncode({
          'cursor': 'a' * 64,
          'items': [for (var i = 1; i <= 2; i++) {
            'job_id': '00000000-0000-4000-8000-00000000000$i',
            'project': 'demo', 'public_ref': 'abcdefghijklmnopqrst', 'action': 'create',
            'project_uuid': null, 'tenant_uuid': null, 'created_by': null,
            'status': i == 1 ? 'queued' : 'running',
          }],
        }), 200);
      }));
      final snapshot = await repository.watch();
      expect(requests, 1);
      expect(snapshot.jobs.map((job) => job.status), ['queued', 'running']);
      repository.close();
    });

    test('a missing watched job fails closed', () async {
      final repository = JobRepository(client: MockClient((_) async =>
        http.Response(jsonEncode({'cursor': 'b' * 64, 'items': []}), 200)));
      addTearDown(repository.close);
      await expectLater(repository.watch(watchedIds: {'00000000-0000-4000-8000-000000000001'}),
          throwsFormatException);
    });
  });

  group('ProjectJobsNotifier', () {
    test('does not lose a tracked job when the initial fetch finishes late',
        () async {
      final initialFetch = Completer<List<Job>>();
      final repository = _ControlledJobRepository(initialFetch);
      final container = ProviderContainer(
        overrides: [jobRepositoryProvider.overrideWithValue(repository)],
      );
      addTearDown(container.dispose);

      container.read(projectJobsProvider);
      final notifier = container.read(projectJobsProvider.notifier);
      notifier.track(
        const Job(
          'job-race',
          project: 'meu_projeto',
          projectUuid: '11111111-1111-4111-8111-111111111111',
          publicRef: 'aaaaaaaaaaaaaaaaaaaa',
          action: 'create',
          createdBy: '33333333-3333-4333-8333-333333333333',
          status: 'running',
          message: 'Pool de conexoes configurado.',
          progress: 60,
          currentStep: 'create_supavisor_tenant',
        ),
        project: 'aaaaaaaaaaaaaaaaaaaa',
        action: 'create',
        createdBy: '33333333-3333-4333-8333-333333333333',
      );

      initialFetch.complete(const []);
      await container.read(projectJobsProvider.future);

      final tracked = container.read(projectJobsProvider).requireValue.single;
      expect(tracked.project, 'meu_projeto');
      expect(tracked.action, 'create');
      expect(tracked.progress, 60);
      expect(tracked.currentStep, 'create_supavisor_tenant');
    });

    test('keeps the richest progress snapshot during concurrent refreshes', () {
      final older = Job(
        'job-merge',
        project: 'meu_projeto',
        projectUuid: '11111111-1111-4111-8111-111111111111',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        status: 'queued',
        progress: 5,
        updatedAt: DateTime.utc(2026, 7, 19, 13, 14, 30),
      );
      final newer = Job(
        'job-merge',
        project: 'meu_projeto',
        projectUuid: '11111111-1111-4111-8111-111111111111',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        status: 'running',
        message: 'Pool de conexoes configurado.',
        progress: 60,
        currentStep: 'create_supavisor_tenant',
        updatedAt: DateTime.utc(2026, 7, 19, 13, 14, 40),
      );

      final merged = mergeJobSnapshots(older, newer);

      expect(merged.project, 'meu_projeto');
      expect(merged.status, 'running');
      expect(merged.progress, 60);
      expect(merged.message, 'Pool de conexoes configurado.');
      expect(merged.currentStep, 'create_supavisor_tenant');
      final stale = mergeJobSnapshots(newer, older);
      expect(stale.progress, 60);
      expect(stale.currentStep, 'create_supavisor_tenant');
    });

    test('rejects a newer regressed percentage instead of mixing two phases', () {
      final current = Job('job-progress', status: 'running', progress: 60,
          currentStep: 'configure_storage', updatedAt: DateTime.utc(2026, 10, 5, 1));
      final regressed = Job('job-progress', status: 'running', progress: 25,
          currentStep: 'export_database', updatedAt: DateTime.utc(2026, 10, 5, 2));
      expect(() => mergeJobSnapshots(current, regressed), throwsFormatException);
    });

    test('takes percentage, phase and terminal state from one fresh snapshot', () {
      final current = Job('job-progress', status: 'running', progress: 60,
          currentStep: 'configure_storage', updatedAt: DateTime.utc(2026, 10, 5, 1));
      final next = Job('job-progress', status: 'done', progress: 100,
          currentStep: 'completed', message: 'Concluído', updatedAt: DateTime.utc(2026, 10, 5, 2));
      final merged = mergeJobSnapshots(current, next);
      expect(merged.status, 'done');
      expect(merged.progress, 100);
      expect(merged.currentStep, 'completed');
      expect(merged.message, 'Concluído');
    });
  });

  group('mergeProjectsWithJobs', () {
    test('rehydrates an in-flight project even when /api/projects is empty',
        () {
      const job = Job(
        'job-1',
        project: 'meu_projeto',
        projectUuid: '11111111-1111-4111-8111-111111111111',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        createdBy: '33333333-3333-4333-8333-333333333333',
        action: 'create',
        status: 'running',
        progress: 10,
      );

      final projects = mergeProjectsWithJobs(
        projects: const [],
        jobs: const [job],
        currentUserId: '33333333-3333-4333-8333-333333333333',
      );

      expect(projects, hasLength(1));
      expect(projects.single['name'], 'meu_projeto');
      expect(projects.single['is_loading'], isTrue);
      expect(projects.single['active_job'], same(job));
    });

    test('annotates existing projects with jobs started by another member', () {
      const job = Job(
        'job-2',
        project: 'compartilhado',
        projectUuid: '11111111-1111-4111-8111-111111111111',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        createdBy: 'other-user',
        action: 'restart',
        status: 'queued',
      );

      final projects = mergeProjectsWithJobs(
        projects: const [
          {
            'name': 'compartilhado',
            'project_uuid': '11111111-1111-4111-8111-111111111111',
            'public_ref': 'aaaaaaaaaaaaaaaaaaaa'
          },
        ],
        jobs: const [job],
        currentUserId: '33333333-3333-4333-8333-333333333333',
      );

      expect(projects, hasLength(1));
      expect(projects.single['active_job'], same(job));
    });

    test('does not leak another user creation into the current project list',
        () {
      const job = Job(
        'job-3',
        project: 'projeto_de_outro_usuario',
        createdBy: 'other-user',
        action: 'create',
        status: 'running',
      );

      final projects = mergeProjectsWithJobs(
        projects: const [],
        jobs: const [job],
        currentUserId: '33333333-3333-4333-8333-333333333333',
      );

      expect(projects, isEmpty);
    });

    test('ignores terminal jobs', () {
      const job = Job(
        'job-4',
        project: 'finalizado',
        createdBy: '33333333-3333-4333-8333-333333333333',
        action: 'create',
        status: 'done',
      );

      final projects = mergeProjectsWithJobs(
        projects: const [],
        jobs: const [job],
        currentUserId: '33333333-3333-4333-8333-333333333333',
      );

      expect(projects, isEmpty);
    });

    test('prefers the running job over a newer queued job', () {
      final running = Job(
        'job-running',
        project: 'meu_projeto',
        projectUuid: '11111111-1111-4111-8111-111111111111',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        status: 'running',
        createdAt: DateTime.utc(2026, 7, 19, 1),
      );
      final queued = Job(
        'job-queued',
        project: 'meu_projeto',
        projectUuid: '11111111-1111-4111-8111-111111111111',
        publicRef: 'aaaaaaaaaaaaaaaaaaaa',
        status: 'queued',
        createdAt: DateTime.utc(2026, 7, 19, 2),
      );

      expect(preferredActiveJob([running, queued]), same(running));
    });
  });
}

class _ControlledJobRepository extends JobRepository {
  _ControlledJobRepository(this.initialFetch)
      : super(client: MockClient((_) async => http.Response('{}', 500)));

  final Completer<List<Job>> initialFetch;

  @override
  Future<JobSnapshot> watch({String? cursor, Set<String> watchedIds = const {},
      RequestCancellation? cancellation}) async {
    if (cursor == null && !initialFetch.isCompleted) {
      return JobSnapshot(await initialFetch.future, 'a' * 64);
    }
    await cancellation!.whenCancelled;
    throw const ApiException(ApiFailureKind.cancelled, 'Cancelled');
  }
}
