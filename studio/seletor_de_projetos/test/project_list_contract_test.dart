import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/models/job.dart';
import 'package:seletor_de_projetos/providers/project_jobs_provider.dart';

const projectUuid = '11111111-1111-4111-8111-111111111111';
const publicRef = 'abcdefghijklmnopqrst';
const project = <String, dynamic>{
  'project_uuid': projectUuid,
  'tenant_uuid': '22222222-2222-4222-8222-222222222222',
  'name': 'technical_project',
  'display_name': 'Meu projeto',
  'public_ref': publicRef,
  'file_size_limit': '52428800',
  'storage_limit_token': '',
  'internal_token_expires_at': null,
  'internal_token_expired': false,
  'internal_token_expiring_soon': false,
  'internal_token_expiry_warning_days': 7,
  'automatic_key_rotation_enabled': true,
  'automatic_key_rotation_lead_days': 7,
  'automatic_key_rotation_due_at': null,
  'automatic_key_rotation_blocked': false,
  'automatic_key_rotation_last_error': null,
  'last_key_rotation_at': null,
  'opaque_api_keys_status': 'ready',
  'opaque_api_key_slot_count': 2,
};

ProjectRepository repositoryFor(Map<String, dynamic> payload) {
  final client = ApiClient(client: MockClient((request) async {
    expect(request.url.path, '/api/projects');
    return http.Response(jsonEncode([payload]), 200,
        headers: {'content-type': 'application/json'});
  }));
  addTearDown(client.close);
  return ProjectRepository(client: client);
}

void main() {
  test('project list consumes the canonical API contract without an id alias',
      () async {
    final projects = await repositoryFor(project).fetchProjects();
    expect(projects.single['project_uuid'], projectUuid);
    expect(projects.single['public_ref'], publicRef);
    expect(projects.single['display_name'], 'Meu projeto');
    expect(projects.single.containsKey('id'), isFalse);
  });

  test('id alone does not substitute for project_uuid', () async {
    final invalid = {...project, 'id': projectUuid}..remove('project_uuid');
    await expectLater(
        repositoryFor(invalid).fetchProjects(), throwsFormatException);
  });

  test('malformed UUID, reference and name fail closed', () async {
    for (final mutation in [
      {'project_uuid': publicRef},
      {'public_ref': 'technical_project'},
      {'display_name': '   '},
    ]) {
      await expectLater(
          repositoryFor({...project, ...mutation}).fetchProjects(),
          throwsFormatException);
    }
  });

  test('loaded projects and provisioning jobs merge by the same canonical UUID',
      () async {
    final projects = await repositoryFor(project).fetchProjects();
    const job = Job('job-1',
        project: 'technical_project',
        projectUuid: projectUuid,
        publicRef: publicRef,
        createdBy: 'user-1',
        action: 'create',
        status: 'running');
    final merged = mergeProjectsWithJobs(
        projects: projects, jobs: [job], currentUserId: 'user-1');
    expect(merged, hasLength(1));
    expect(merged.single['active_job'], same(job));
    expect(merged.single['project_uuid'], projectUuid);
    expect(merged.single['display_name'], 'Meu projeto');
    final placeholder = mergeProjectsWithJobs(
            projects: [], jobs: [job], currentUserId: 'user-1')
        .single;
    expect(placeholder['project_uuid'], projectUuid);
    expect(placeholder.containsKey('id'), isFalse);
  });
}
