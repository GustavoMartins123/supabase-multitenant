import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/services/project_service.dart';
import 'package:seletor_de_projetos/services/step_up_authentication_service.dart';

void main() {
  testWidgets(
      'project deletion uses personal step-up grant, never global password',
      (tester) async {
    http.Request? deleteRequest;
    final apiClient = ApiClient(
      client: MockClient((request) async {
        deleteRequest = request;
        return http.Response(
          jsonEncode({
            'job_id': '33333333-3333-4333-8333-333333333333',
            'project': 'demo_project',
            'action': 'delete',
            'status': 'queued',
          }),
          202,
          headers: const {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(apiClient.close);

    final completed = Completer<bool>();
    String? passwordSeen;
    StepUpAction? actionSeen;
    String? projectSeen;
    String? resourceSeen;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () async {
                completed.complete(
                  await ProjectService.confirmAndDeleteProject(
                    context,
                    'demo_project',
                    requestStepUpToken: ({
                      required password,
                      required action,
                      required projectRef,
                      required resourceId,
                    }) async {
                      passwordSeen = password;
                      actionSeen = action;
                      projectSeen = projectRef;
                      resourceSeen = resourceId;
                      return 'su1.delete-grant.signature';
                    },
                    submittedJobWaiter: (_) async => const JobWaitResult(
                      ok: true,
                      status: 'done',
                      message: 'Projeto excluido.',
                    ),
                    apiClient: apiClient,
                  ),
                );
              },
              child: const Text('Excluir projeto'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Excluir projeto'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Confirmar Exclusão'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('step-up-authentication-dialog')),
      findsOneWidget,
    );
    await tester.enterText(
      find.byKey(const ValueKey('step-up-password-field')),
      'current-account-password',
    );
    await tester.tap(find.text('Reautenticar'));
    await tester.pumpAndSettle();

    expect(passwordSeen, 'current-account-password');
    expect(actionSeen, StepUpAction.deleteProject);
    expect(projectSeen, 'demo_project');
    expect(resourceSeen, 'demo_project');
    expect(deleteRequest?.method, 'DELETE');
    expect(deleteRequest?.url.path, '/api/admin/projects/demo_project');
    expect(
      deleteRequest?.headers['X-Step-Up-Token'],
      'su1.delete-grant.signature',
    );
    expect(deleteRequest?.headers, isNot(contains('X-Delete-Password')));

    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(await completed.future, isTrue);
    expect(find.byKey(const ValueKey('step-up-password-field')), findsNothing);
  });
}
