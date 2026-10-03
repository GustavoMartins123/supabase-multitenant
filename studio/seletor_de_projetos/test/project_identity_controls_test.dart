import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/models/project_docker_status.dart';
import 'package:seletor_de_projetos/models/project_member.dart';
import 'package:seletor_de_projetos/project_settings_dialog.dart';
import 'package:seletor_de_projetos/providers/config_provider.dart';
import 'package:seletor_de_projetos/providers/project_jobs_provider.dart';
import 'package:seletor_de_projetos/providers/project_list_provider.dart';
import 'package:seletor_de_projetos/providers/project_settings_provider.dart';
import 'package:seletor_de_projetos/session.dart';

const projectRef = 'abcdefghijklmnopqrst';

class FixtureConfig extends ConfigNotifier {
  @override
  Future<Map<String, dynamic>> build() async => {
        'server_domain': 'https://example.test',
      };
}

class FixtureProjectList extends ProjectListNotifier {
  @override
  Future<List<Map<String, dynamic>>> build() async => [];

  @override
  Future<void> refresh({bool throwOnError = false}) async {}
}

void main() {
  testWidgets('renaming the project and generating a URL are separate controls',
      (tester) async {
    Session()
      ..myId = '11111111-1111-4111-8111-111111111111'
      ..isSysAdmin = true;
    final requests = <http.Request>[];
    final client = ApiClient(client: MockClient((request) async {
      requests.add(request);
      return http.Response(
        jsonEncode({
          'project': projectRef,
          'display_name': 'Meu novo nome',
          'status': 'updated',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }));
    addTearDown(client.close);
    tester.view.physicalSize = const Size(1280, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(ProviderScope(
      overrides: [
        configProvider.overrideWith(FixtureConfig.new),
        projectListProvider.overrideWith(FixtureProjectList.new),
        projectRepositoryProvider
            .overrideWithValue(ProjectRepository(client: client)),
        projectMembersProvider(projectRef).overrideWith((ref) async => [
              ProjectMember(userId: Session().myId, role: 'admin'),
            ]),
        activeProjectJobProvider(projectRef).overrideWith((ref) => null),
        projectStatusProvider(projectRef).overrideWith((ref) async =>
            ProjectDockerStatus(status: 'running', running: 3, total: 3)),
      ],
      child: const MaterialApp(
        home: Scaffold(
          body: ProjectSettingsDialog(
            ref: projectRef,
            displayName: 'Meu nome atual',
            automaticKeyRotationEnabled: true,
            automaticKeyRotationBlocked: false,
            automaticKeyRotationLeadDays: 7,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Gerar nova URL'), findsOneWidget);
    expect(find.text('Renomear projeto'), findsOneWidget);
    expect(find.text('https://example.test/$projectRef'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('project-name-field')), 'Meu novo nome');
    await tester.pump();
    await tester.ensureVisible(find.text('Renomear projeto'));
    await tester.tap(find.text('Renomear projeto'));
    await tester.pumpAndSettle();
    expect(requests, hasLength(1));
    expect(requests.single.method, 'PATCH');
    expect(requests.single.url.path, '/api/projects/$projectRef/display-name');
    expect(jsonDecode(requests.single.body), {'display_name': 'Meu novo nome'});
    expect(find.text('https://example.test/$projectRef'), findsOneWidget);

    await tester.ensureVisible(find.text('Gerar nova URL'));
    await tester.tap(find.text('Gerar nova URL'));
    await tester.pumpAndSettle();
    expect(find.text('Gerar nova URL do projeto'), findsOneWidget);
    expect(requests, hasLength(1));
    expect(tester.takeException(), isNull);
  });
}
