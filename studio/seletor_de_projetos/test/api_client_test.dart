import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';

void main() {
  tearDown(() => ApiClient.unauthorizedHandler = null);

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

  test('detecta quando o navegador seguiu a API ate a pagina de login',
      () async {
    var redirects = 0;
    ApiClient.unauthorizedHandler = () => redirects++;
    final client = ApiClient(client: _AuthenticationRedirectClient());
    addTearDown(client.close);

    await expectLater(
      client.get(Uri.parse('https://studio.test/api/user/me')),
      throwsA(
        isA<ApiException>()
            .having(
              (error) => error.kind,
              'kind',
              ApiFailureKind.unauthorized,
            )
            .having((error) => error.uri?.path, 'uri', '/api/user/me'),
      ),
    );
    expect(redirects, 1);
  });

  test('rejeita HTML em resposta 200 de API sem expor o documento', () async {
    final client = ApiClient(
      client: MockClient(
        (_) async => http.Response(
          '<!doctype html><html><body>pagina indevida</body></html>',
          200,
          headers: {'content-type': 'text/html; charset=utf-8'},
        ),
      ),
    );
    addTearDown(client.close);

    await expectLater(
      client.get(Uri.parse('https://studio.test/api/jobs')),
      throwsA(
        isA<ApiException>()
            .having(
              (error) => error.kind,
              'kind',
              ApiFailureKind.invalidResponse,
            )
            .having(
              (error) => error.message.contains('<html>'),
              'does not expose HTML',
              isFalse,
            ),
      ),
    );
  });

  test('decodifica objetos JSON e converte erro de sintaxe em ApiException',
      () {
    final valid = http.Response(
      jsonEncode({'ok': true}),
      200,
      headers: {'content-type': 'application/json'},
    );
    expect(
      decodeJsonObject(valid, context: 'Teste'),
      {'ok': true},
    );

    final invalid = http.Response(
      '{',
      200,
      headers: {'content-type': 'application/json'},
    );
    expect(
      () => decodeJsonObject(invalid, context: 'Teste'),
      throwsA(
        isA<ApiException>().having(
          (error) => error.kind,
          'kind',
          ApiFailureKind.invalidResponse,
        ),
      ),
    );
  });

  test('solicita JSON por padrao em todas as rotas de API', () async {
    late String accept;
    final client = ApiClient(
      client: MockClient((request) async {
        accept = request.headers['accept'] ?? '';
        return http.Response('{}', 200);
      }),
    );
    addTearDown(client.close);

    await client.get(Uri.parse('https://studio.test/api/config'));
    expect(accept, 'application/json');
  });
}

final class _AuthenticationRedirectClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    request.finalize();
    return _ResponseWithUrl(
      request: request,
      url: Uri.parse(
        'https://studio.test/auth?rd=https%3A%2F%2Fstudio.test%2F',
      ),
    );
  }
}

final class _ResponseWithUrl extends http.StreamedResponse
    implements http.BaseResponseWithUrl {
  _ResponseWithUrl({
    required http.BaseRequest request,
    required this.url,
  }) : super(
          Stream.value(utf8.encode('<!doctype html><html></html>')),
          200,
          request: request,
          headers: {'content-type': 'text/html; charset=utf-8'},
        );

  @override
  final Uri url;
}
