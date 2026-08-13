import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/services/step_up_authentication_service.dart';

void main() {
  test('requests an exact action-bound grant using the current password',
      () async {
    http.Request? captured;
    final service = StepUpAuthenticationService(
      client: ApiClient(
        client: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'step_up_token': 'su1.payload.signature',
              'expires_in': 300,
            }),
            200,
            headers: const {'content-type': 'application/json'},
          );
        }),
      ),
    );
    addTearDown(service.close);

    final token = await service.requestToken(
      password: 'my-current-password',
      action: StepUpAction.deleteProject,
      projectRef: 'demo_project',
      resourceId: 'demo_project',
    );

    expect(token, 'su1.payload.signature');
    expect(captured?.method, 'POST');
    expect(captured?.url.path, '/api/security/step-up');
    final payload = jsonDecode(captured!.body) as Map<String, dynamic>;
    expect(payload, {
      'password': 'my-current-password',
      'action': 'delete_project',
      'project': 'demo_project',
      'resource': 'demo_project',
    });
    expect(captured?.headers, isNot(contains('X-Delete-Password')));
  });
}
