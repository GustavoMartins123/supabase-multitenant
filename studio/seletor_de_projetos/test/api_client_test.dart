import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';

void main() {
  test('classifica resposta HTTP e preserva a mensagem da API', () async {
    final client = ApiClient(
      client: MockClient(
        (_) async => http.Response(
          jsonEncode({'detail': 'Acesso negado'}),
          403,
        ),
      ),
    );
    addTearDown(client.close);

    final response = await client.get(Uri.parse('https://example.test/api'));
    final error = ApiException.fromResponse(response);

    expect(error.kind, ApiFailureKind.forbidden);
    expect(error.statusCode, 403);
    expect(error.message, 'Acesso negado');
  });

  test('interrompe uma requisicao que excede o tempo limite', () async {
    final client = ApiClient(
      client: MockClient((_) async {
        await Future<void>.delayed(const Duration(seconds: 1));
        return http.Response('{}', 200);
      }),
      timeout: const Duration(milliseconds: 20),
    );
    addTearDown(client.close);

    await expectLater(
      client.get(Uri.parse('https://example.test/slow')),
      throwsA(
        isA<ApiException>().having(
          (error) => error.kind,
          'kind',
          ApiFailureKind.timeout,
        ),
      ),
    );
  });

  test('cancela explicitamente uma requisicao ativa', () async {
    final cancellation = RequestCancellation();
    final started = Completer<void>();
    final client = ApiClient(
      client: MockClient((_) async {
        started.complete();
        await Future<void>.delayed(const Duration(seconds: 1));
        return http.Response('{}', 200);
      }),
    );
    addTearDown(client.close);

    final request = client.get(
      Uri.parse('https://example.test/cancel'),
      cancellation: cancellation,
    );
    await started.future;
    cancellation.cancel();

    await expectLater(
      request,
      throwsA(
        isA<ApiException>().having(
          (error) => error.kind,
          'kind',
          ApiFailureKind.cancelled,
        ),
      ),
    );
  });
}
