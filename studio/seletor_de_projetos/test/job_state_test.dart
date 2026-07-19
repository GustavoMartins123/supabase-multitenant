import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/job_repository.dart';
import 'package:seletor_de_projetos/models/job.dart';
import 'package:seletor_de_projetos/providers/project_jobs_provider.dart';

void main() {
  group('Job', () {
    test('parses the durable job payload returned by the API', () {
      final job = Job.fromJson({
        'job_id': 'job-1',
        'project': 'meu_projeto',
        'project_uuid': 'project-uuid',
        'tenant_uuid': 'tenant-uuid',
        'created_by': 'user-1',
        'action': 'create',
        'status': 'running',
        'message': 'Provisionando infraestrutura do projeto...',
        'progress': 10.0,
        'current_step': 'provision_infrastructure',
        'total_steps': 3,
        'created_at': '2026-07-19T03:08:48.079739+00:00',
      });

      expect(job.id, 'job-1');
      expect(job.project, 'meu_projeto');
      expect(job.action, 'create');
      expect(job.tenantUuid, 'tenant-uuid');
      expect(job.progress, 10);
      expect(job.currentStep, 'provision_infrastructure');
      expect(job.isInFlight, isTrue);
      expect(job.createdAt, isNotNull);
    });
  });

  group('JobRepository', () {
    test('rehydrates both queued and running jobs', () async {
      final requestedStatuses = <String>{};
      final repository = JobRepository(
        client: MockClient((request) async {
          final status = request.url.queryParameters['status']!;
          requestedStatuses.add(status);
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'job_id': 'job-$status',
                  'project': 'project-$status',
                  'created_by': 'user-1',
                  'action': 'create',
                  'status': status,
                  'progress': status == 'running' ? 40 : 0,
                },
              ],
            }),
            200,
          );
        }),
      );

      final jobs = await repository.fetchInFlightJobs();

      expect(requestedStatuses, {'queued', 'running'});
      expect(jobs.map((job) => job.status), containsAll(['queued', 'running']));
      repository.close();
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
          status: 'running',
          message: 'Pool de conexoes configurado.',
          progress: 60,
          currentStep: 'create_supavisor_tenant',
        ),
        project: 'meu_projeto',
        action: 'create',
        createdBy: 'user-1',
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
        status: 'queued',
        progress: 5,
        updatedAt: DateTime.utc(2026, 7, 19, 13, 14, 30),
      );
      final newer = Job(
        'job-merge',
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
    });
  });

  group('mergeProjectsWithJobs', () {
    test('rehydrates an in-flight project even when /api/projects is empty',
        () {
      const job = Job(
        'job-1',
        project: 'meu_projeto',
        createdBy: 'user-1',
        action: 'create',
        status: 'running',
        progress: 10,
      );

      final projects = mergeProjectsWithJobs(
        projects: const [],
        jobs: const [job],
        currentUserId: 'user-1',
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
        createdBy: 'other-user',
        action: 'restart',
        status: 'queued',
      );

      final projects = mergeProjectsWithJobs(
        projects: const [
          {'name': 'compartilhado', 'anon_token': 'token'},
        ],
        jobs: const [job],
        currentUserId: 'user-1',
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
        currentUserId: 'user-1',
      );

      expect(projects, isEmpty);
    });

    test('ignores terminal jobs', () {
      const job = Job(
        'job-4',
        project: 'finalizado',
        createdBy: 'user-1',
        action: 'create',
        status: 'done',
      );

      final projects = mergeProjectsWithJobs(
        projects: const [],
        jobs: const [job],
        currentUserId: 'user-1',
      );

      expect(projects, isEmpty);
    });

    test('prefers the running job over a newer queued job', () {
      final running = Job(
        'job-running',
        project: 'meu_projeto',
        status: 'running',
        createdAt: DateTime.utc(2026, 7, 19, 1),
      );
      final queued = Job(
        'job-queued',
        project: 'meu_projeto',
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
  Future<List<Job>> fetchInFlightJobs() => initialFetch.future;
}
