import 'package:flutter_test/flutter_test.dart';
import 'package:projects_api_client/api.dart' as generated;
import 'package:seletor_de_projetos/models/project_identity.dart';
import 'package:seletor_de_projetos/models/project_info.dart';

import 'project_list_contract_test.dart' show project;

void main() {
  test('nullable identity is explicit, not a substituted identifier', () {
    final identity = ProjectIdentity.fromJson({...project, 'tenant_uuid': null});
    expect(identity.tenantUuid, isNull);
    expect(() => ProjectIdentity.fromJson({...project}..remove('tenant_uuid')),
        throwsFormatException);
    expect(() => ProjectIdentity.fromJson({...project, 'tenant_uuid': 'bad'}),
        throwsFormatException);
  });

  test('display-name length uses Unicode codepoints just like the API', () {
    expect(ProjectIdentity.fromJson({...project, 'display_name': '🌍' * 80}).displayName,
        '🌍' * 80);
    expect(() => ProjectIdentity.fromJson({...project, 'display_name': '🌍' * 81}),
        throwsFormatException);
  });

  test('admin projection uses project_uuid without an id alias', () {
    final info = ProjectInfo.fromJson({...project, 'status': 'running',
      'running_containers': 3, 'total_containers': 3});
    expect(info.projectUuid, project['project_uuid']);
    expect(() => ProjectInfo.fromJson({...project, 'id': project['project_uuid']}
      ..remove('project_uuid')), throwsFormatException);
  });

  test('generated client accepts required null values and rejects missing fields', () {
    final parsed = generated.ProjectListItem.fromJson(project)!;
    expect(parsed.automaticKeyRotationDueAt, isNull);
    expect(parsed.internalTokenExpiresAt, isNull);
    expect(() => generated.ProjectListItem.fromJson({...project}..remove('tenant_uuid')),
        throwsFormatException);
    expect(() => generated.ProjectListItem.fromJson({...project, 'public_ref': null}),
        throwsFormatException);
  });
}
