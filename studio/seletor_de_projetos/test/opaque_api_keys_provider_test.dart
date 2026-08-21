import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/providers/opaque_api_keys_provider.dart';

void main() {
  test('claim keeps the key readable and marks it delivered',
      () async {
    final api = _OpaqueApiKeysApi();
    final repository = ProjectRepository(
      client: ApiClient(client: MockClient(api.handle)),
    );
    addTearDown(repository.close);
    final container = ProviderContainer.test(
      overrides: [projectRepositoryProvider.overrideWithValue(repository)],
    );
    final provider = opaqueApiKeysProvider('project-ref');
    final subscription = container.listen(provider, (_, __) {});
    addTearDown(subscription.close);

    final initial = await container.read(provider.future);
    expect(initial.reveals.single.keyId, 'key-1');
    expect(api.getCalls, 3);

    final claimFuture = container
        .read(provider.notifier)
        .claimReveal(initial.reveals.single.keyId);
    expect(
      container.read(provider).requireValue.isRevealBusy('key-1'),
      isTrue,
    );

    final secret = await claimFuture;
    final claimed = container.read(provider).requireValue;

    expect(secret, _OpaqueApiKeysApi.secret);
    expect(api.claimCalls, 1);
    expect(api.getCalls, 3);
    expect(claimed.reveals.single.keyId, 'key-1');
    expect(claimed.reveals.single.revealedAt, isNotNull);
    expect(claimed.hasActiveOperation, isFalse);
  });
}

final class _OpaqueApiKeysApi {
  static const secret = 'sb_publishable_one_time_plaintext';

  int getCalls = 0;
  int claimCalls = 0;
  bool claimed = false;

  Future<http.Response> handle(http.Request request) async {
    final path = request.url.path;
    if (request.method == 'GET') {
      getCalls++;
      if (path.endsWith('/opaque-api-keys/migration')) {
        return _json({
          'status': 'prepared',
          'pending_key_count': 2,
          'confirmed_pending_key_count': 0,
        });
      }
      if (path.endsWith('/api-key-slots')) {
        return _json({
          'slots': [_slotJson(revealed: claimed)],
        });
      }
      if (path.endsWith('/api-key-reveals')) {
        return _json({
          'reveals': claimed ? <Object>[] : [_revealJson()],
        });
      }
    }
    if (request.method == 'POST' && path.endsWith('/key-1/claim')) {
      claimCalls++;
      claimed = true;
      return _json({'api_key': secret});
    }
    return _json({'detail': 'unexpected ${request.method} $path'}, 500);
  }

  static Map<String, dynamic> _slotJson({required bool revealed}) => {
        'id': 'slot-1',
        'name': 'default-publishable',
        'kind': 'publishable',
        'role': 'anon',
        'allowed_services': ['rest'],
        'automatic_rotation_enabled': true,
        'rotation_interval_days': 90,
        'status': 'active',
        'created_at': '2026-08-12T10:00:00Z',
        'automatic_rotation_blocked_at': null,
        'automatic_rotation_last_error': null,
        'keys': [
          {
            'id': 'key-1',
            'token_hint': 'sb_publishable_...test',
            'status': 'pending',
            'currently_accepted': false,
            'created_at': '2026-08-12T10:00:00Z',
            'activate_at': '2026-08-19T10:00:00Z',
            'expires_at': '2026-11-10T10:00:00Z',
            'activated_at': null,
            'revoked_at': null,
            'last_used_at': null,
            'revealed_at': revealed ? '2026-08-12T10:05:00Z' : null,
            'confirmed_at': null,
            'rotation_trigger': 'initial',
          },
        ],
      };

  static Map<String, dynamic> _revealJson() => {
        'key_id': 'key-1',
        'slot_id': 'slot-1',
        'slot_name': 'default-publishable',
        'kind': 'publishable',
        'created_at': '2026-08-12T10:00:00Z',
        'key_status': 'active',
        'revealed_at': null,
      };

  static http.Response _json(Object body, [int statusCode = 200]) =>
      http.Response(
        jsonEncode(body),
        statusCode,
        headers: const {'content-type': 'application/json'},
      );
}
