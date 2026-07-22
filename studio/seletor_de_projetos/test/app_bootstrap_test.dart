import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/app_bootstrap.dart';
import 'package:seletor_de_projetos/data/api_client.dart';

void main() {
  tearDown(() => ApiClient.unauthorizedHandler = null);

  test('bootstrap sem administrador nao consulta uma sessao inexistente',
      () async {
    final paths = <String>[];
    final client = ApiClient(
      client: MockClient((request) async {
        paths.add(request.url.path);
        return http.Response(
          jsonEncode({'needs_admin': true}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(client.close);

    final result = await loadAppBootstrap(client);

    expect(result.needsBootstrapAdmin, isTrue);
    expect(result.profile, isNull);
    expect(paths, ['/api/bootstrap/status']);
  });

  test('bootstrap autenticado carrega e valida o perfil completo', () async {
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/api/bootstrap/status') {
          return http.Response(
            jsonEncode({'needs_admin': false}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({
            'user_id': '11111111-2222-3333-4444-555555555555',
            'username': 'admin',
            'email': 'admin@example.test',
            'display_name': 'Admin',
            'groups': ['active', 'admin'],
            'is_active': true,
            'is_admin': true,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(client.close);

    final result = await loadAppBootstrap(client);

    expect(result.needsBootstrapAdmin, isFalse);
    expect(result.accessDenied, isFalse);
    expect(result.profile?.username, 'admin');
    expect(result.profile?.isAdmin, isTrue);
  });

  test('bootstrap diferencia acesso negado de sessao expirada', () async {
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/api/bootstrap/status') {
          return http.Response(
            jsonEncode({'needs_admin': false}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 403);
      }),
    );
    addTearDown(client.close);

    final result = await loadAppBootstrap(client);

    expect(result.accessDenied, isTrue);
    expect(result.profile, isNull);
  });

  test('bootstrap encerra em unauthorized quando o logout remove a sessao',
      () async {
    var redirects = 0;
    ApiClient.unauthorizedHandler = () => redirects++;
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/api/bootstrap/status') {
          return http.Response(
            jsonEncode({'needs_admin': false}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({'error': 'authentication required'}),
          401,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(client.close);

    await expectLater(
      loadAppBootstrap(client),
      throwsA(
        isA<ApiException>().having(
          (error) => error.kind,
          'kind',
          ApiFailureKind.unauthorized,
        ),
      ),
    );
    expect(redirects, 1);
  });

  test('bootstrap rejeita contrato incompleto antes de montar a pagina',
      () async {
    final client = ApiClient(
      client: MockClient((request) async {
        final payload = request.url.path == '/api/bootstrap/status'
            ? {'needs_admin': false}
            : {'username': 'admin'};
        return http.Response(
          jsonEncode(payload),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(client.close);

    await expectLater(
      loadAppBootstrap(client),
      throwsA(
        isA<ApiException>().having(
          (error) => error.kind,
          'kind',
          ApiFailureKind.invalidResponse,
        ),
      ),
    );
  });
}
