import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/models/opaque_api_key.dart';

void main() {
  Map<String, dynamic> slotJson() => {
    'id': '11111111-1111-4111-8111-111111111111', 'name': 'web_client',
    'kind': 'publishable', 'role': 'anon', 'application_ref': 'abcdefghijklmnopqrst',
    'allowed_services': ['rest'], 'automatic_rotation_enabled': false,
    'rotation_interval_days': null, 'status': 'active',
    'created_at': '2026-08-12T12:00:00Z', 'keys': [],
  };

  test('publishable configuration reference is explicit and canonical', () {
    expect(OpaqueApiKeySlot.fromJson(slotJson()).applicationRef, 'abcdefghijklmnopqrst');
    for (final value in [null, '', 'a' * 19, 'a' * 20 + '\n', 'A' * 20, 123]) {
      expect(() => OpaqueApiKeySlot.fromJson({...slotJson(), 'application_ref': value}),
          throwsFormatException);
    }
    expect(() => OpaqueApiKeySlot.fromJson(slotJson()..remove('application_ref')),
        throwsFormatException);
  });

  test('secret slot cannot expose an application configuration reference', () {
    final secret = {...slotJson(), 'kind': 'secret', 'role': 'service_role'};
    expect(() => OpaqueApiKeySlot.fromJson(secret), throwsFormatException);
    expect(OpaqueApiKeySlot.fromJson({...secret, 'application_ref': null}).applicationRef,
        isNull);
  });
  test('serializa slot e chave sem expiração temporal', () {
    final slot = OpaqueApiKeySlot.fromJson({
      'id': '11111111-1111-4111-8111-111111111111',
      'name': 'web-production',
      'kind': 'publishable',
      'application_ref': 'abcdefghijklmnopqrst',
      'role': 'anon',
      'allowed_services': ['auth', 'rest'],
      'automatic_rotation_enabled': false,
      'rotation_interval_days': null,
      'status': 'active',
      'created_at': '2026-08-12T12:00:00Z',
      'automatic_rotation_blocked_at': null,
      'automatic_rotation_last_error': null,
      'keys': [
        {
          'id': '22222222-2222-4222-8222-222222222222',
          'token_hint': 'sb_publishable_abc...xyz',
          'status': 'active',
          'currently_accepted': true,
          'created_at': '2026-08-12T12:00:00Z',
          'activate_at': null,
          'expires_at': null,
          'activated_at': '2026-08-12T12:00:00Z',
          'revoked_at': null,
          'last_used_at': null,
          'revealed_at': null,
          'confirmed_at': null,
          'rotation_trigger': 'manual',
        },
      ],
    });

    expect(slot.rotationIntervalDays, isNull);
    expect(slot.automaticRotationEnabled, isFalse);
    expect(slot.keys.single.expiresAt, isNull);
    expect(slot.keys.single.currentlyAccepted, isTrue);
  });

  test('resposta de emissão aceita expires_at nulo', () {
    final issued = IssuedOpaqueApiKey.fromJson({
      'slot_id': '11111111-1111-4111-8111-111111111111',
      'key_id': '22222222-2222-4222-8222-222222222222',
      'api_key': 'sb_publishable_plaintext-once',
      'token_hint': 'sb_publishable_abc...xyz',
      'kind': 'publishable',
      'status': 'active',
      'activate_at': null,
      'expires_at': null,
    });

    expect(issued.expiresAt, isNull);
  });

  test('contrato exige expires_at mesmo quando nullable', () {
    expect(
      () => IssuedOpaqueApiKey.fromJson({
        'slot_id': '11111111-1111-4111-8111-111111111111',
        'key_id': '22222222-2222-4222-8222-222222222222',
        'api_key': 'sb_publishable_plaintext-once',
        'token_hint': 'sb_publishable_abc...xyz',
        'kind': 'publishable',
        'status': 'active',
        'activate_at': null,
      }),
      throwsFormatException,
    );
  });
}
