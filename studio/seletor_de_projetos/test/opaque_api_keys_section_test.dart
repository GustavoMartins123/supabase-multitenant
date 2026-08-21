import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seletor_de_projetos/data/api_client.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/services/step_up_authentication_service.dart';
import 'package:seletor_de_projetos/widgets/project_settings/opaque_api_keys_section.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'claim keeps content mounted and forgets plaintext when modal closes',
      (tester) async {
    final api = _ControlledOpaqueApiKeysApi();
    final repository = ProjectRepository(
      client: ApiClient(client: MockClient(api.handle)),
    );
    addTearDown(repository.close);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (_) async => null);
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [projectRepositoryProvider.overrideWithValue(repository)],
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: OpaqueApiKeysSection(
                projectRef: 'project-ref',
                canManage: true,
                projectBusy: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Migracao preparada; JWT legado ainda esta ativo'),
        findsOneWidget);
    expect(find.text('default-publishable · publishable'), findsOneWidget);

    await tester.tap(find.text('Ver e copiar'));
    await tester.pump();

    expect(api.claimCalls, 1);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(
      find.byKey(const ValueKey('opaque-reveal-progress-key-1')),
      findsOneWidget,
    );
    expect(find.text('Migracao preparada; JWT legado ainda esta ativo'),
        findsOneWidget);
    expect(find.text('default-publishable · publishable'), findsOneWidget);

    api.completeClaim();
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('claimed-opaque-api-key-dialog')),
      findsOneWidget,
    );
    expect(find.text(_ControlledOpaqueApiKeysApi.secret), findsOneWidget);
    expect(api.claimCalls, 1);
    expect(find.byType(CircularProgressIndicator), findsNothing);

    await tester.tap(find.text('Fechar'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('claimed-opaque-api-key-dialog')),
      findsNothing,
    );
    expect(find.text(_ControlledOpaqueApiKeysApi.secret), findsNothing);
    expect(find.text('Ver e copiar'), findsOneWidget);
    expect(api.claimCalls, 1);
    expect(api.getCalls, 6);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('project member can reveal publishable without admin controls',
      (tester) async {
    final api = _ControlledOpaqueApiKeysApi();
    final repository = ProjectRepository(
      client: ApiClient(client: MockClient(api.handle)),
    );
    addTearDown(repository.close);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (_) async => null);
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [projectRepositoryProvider.overrideWithValue(repository)],
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: OpaqueApiKeysSection(
                projectRef: 'project-ref',
                canManage: false,
                projectBusy: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('default-publishable · publishable'), findsOneWidget);
    expect(find.text('Ver e copiar'), findsOneWidget);
    expect(find.text('Rotacionar agora'), findsNothing);
    expect(find.text('Revogar slot'), findsNothing);

    await tester.tap(find.text('Ver e copiar'));
    await tester.pump();
    expect(api.claimCalls, 1);
    expect(
      find.byKey(const ValueKey('step-up-authentication-dialog')),
      findsNothing,
    );

    api.completeClaim();
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('claimed-opaque-api-key-dialog')),
      findsOneWidget,
    );
  });

  testWidgets('secret reveal reauthenticates and sends one action-bound grant',
      (tester) async {
    final api = _SecretOpaqueApiKeysApi();
    final repository = ProjectRepository(
      client: ApiClient(client: MockClient(api.handle)),
    );
    final stepUpApi = _StepUpApi();
    final stepUpService = StepUpAuthenticationService(
      client: ApiClient(client: MockClient(stepUpApi.handle)),
    );
    addTearDown(repository.close);
    addTearDown(stepUpService.close);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (_) async => null);
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          projectRepositoryProvider.overrideWithValue(repository),
          stepUpAuthenticationServiceProvider.overrideWithValue(stepUpService),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: OpaqueApiKeysSection(
                projectRef: 'project-ref',
                canManage: true,
                projectBusy: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Ver e copiar'));
    await tester.pumpAndSettle();
    expect(api.claimCalls, 0);
    expect(
      find.byKey(const ValueKey('step-up-authentication-dialog')),
      findsOneWidget,
    );

    await tester.enterText(
      find.byKey(const ValueKey('step-up-password-field')),
      'current-user-password',
    );
    await tester.tap(find.text('Reautenticar'));
    await tester.pumpAndSettle();

    expect(stepUpApi.calls, 1);
    expect(stepUpApi.payload?['password'], 'current-user-password');
    expect(stepUpApi.payload?['action'], 'reveal_secret_key');
    expect(stepUpApi.payload?['project'], 'project-ref');
    expect(stepUpApi.payload?['resource'], _SecretOpaqueApiKeysApi.keyId);
    expect(api.claimCalls, 1);
    expect(api.claimStepUpToken, _StepUpApi.token);
    expect(
      find.byKey(const ValueKey('claimed-opaque-api-key-dialog')),
      findsOneWidget,
    );
    expect(find.text(_SecretOpaqueApiKeysApi.secret), findsOneWidget);
    expect(find.byKey(const ValueKey('step-up-password-field')), findsNothing);
  });
}

final class _ControlledOpaqueApiKeysApi {
  static const secret = 'sb_publishable_widget_one_time_plaintext';

  final Completer<http.Response> _claim = Completer<http.Response>();
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
          'confirmed_pending_key_count': claimed ? 1 : 0,
        });
      }
      if (path.endsWith('/api-key-slots')) {
        return _json({
          'slots': [_slotJson(revealed: claimed)],
        });
      }
      if (path.endsWith('/api-key-reveals')) {
        return _json({
          'reveals': [_revealJson(revealed: claimed)],
        });
      }
    }
    if (request.method == 'POST' && path.endsWith('/key-1/claim')) {
      claimCalls++;
      final response = await _claim.future;
      claimed = true;
      return response;
    }
    return _json({'detail': 'unexpected ${request.method} $path'}, 500);
  }

  void completeClaim() {
    _claim.complete(_json({'api_key': secret}));
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

  static Map<String, dynamic> _revealJson({bool revealed = false}) => {
        'key_id': 'key-1',
        'slot_id': 'slot-1',
        'slot_name': 'default-publishable',
        'kind': 'publishable',
        'created_at': '2026-08-12T10:00:00Z',
        'key_status': 'pending',
        'revealed_at': revealed ? '2026-08-12T10:05:00Z' : null,
      };

  static http.Response _json(Object body, [int statusCode = 200]) =>
      http.Response(
        jsonEncode(body),
        statusCode,
        headers: const {'content-type': 'application/json'},
      );
}

final class _SecretOpaqueApiKeysApi {
  static const keyId = '11111111-1111-4111-8111-111111111111';
  static const slotId = '22222222-2222-4222-8222-222222222222';
  static const secret = 'sb_secret_widget_one_time_plaintext';

  int claimCalls = 0;
  String? claimStepUpToken;
  bool claimed = false;

  Future<http.Response> handle(http.Request request) async {
    final path = request.url.path;
    if (request.method == 'GET') {
      if (path.endsWith('/opaque-api-keys/migration')) {
        return _json({
          'status': 'active',
          'pending_key_count': 0,
          'confirmed_pending_key_count': 0,
        });
      }
      if (path.endsWith('/api-key-slots')) {
        return _json({
          'slots': [
            {
              'id': slotId,
              'name': 'backend-worker',
              'kind': 'secret',
              'role': 'service_role',
              'allowed_services': ['rest'],
              'automatic_rotation_enabled': false,
              'rotation_interval_days': null,
              'status': 'active',
              'created_at': '2026-08-12T10:00:00Z',
              'automatic_rotation_blocked_at': null,
              'automatic_rotation_last_error': null,
              'keys': [
                {
                  'id': keyId,
                  'token_hint': 'sb_secret_...test',
                  'status': 'active',
                  'currently_accepted': true,
                  'created_at': '2026-08-12T10:00:00Z',
                  'activate_at': null,
                  'expires_at': null,
                  'activated_at': '2026-08-12T10:00:00Z',
                  'revoked_at': null,
                  'last_used_at': null,
                  'revealed_at': claimed ? '2026-08-12T10:05:00Z' : null,
                  'confirmed_at': null,
                  'rotation_trigger': 'initial',
                },
              ],
            },
          ],
        });
      }
      if (path.endsWith('/api-key-reveals')) {
        return _json({
          'reveals': [
            {
              'key_id': keyId,
              'slot_id': slotId,
              'slot_name': 'backend-worker',
              'kind': 'secret',
              'created_at': '2026-08-12T10:00:00Z',
              'key_status': 'active',
              'revealed_at': claimed ? '2026-08-12T10:05:00Z' : null,
            },
          ],
        });
      }
    }
    if (request.method == 'POST' && path.endsWith('/$keyId/claim')) {
      claimCalls++;
      claimStepUpToken = request.headers['X-Step-Up-Token'];
      claimed = true;
      return _json({'api_key': secret});
    }
    return _json({'detail': 'unexpected ${request.method} $path'}, 500);
  }

  static http.Response _json(Object body, [int statusCode = 200]) =>
      http.Response(
        jsonEncode(body),
        statusCode,
        headers: const {'content-type': 'application/json'},
      );
}

final class _StepUpApi {
  static const token = 'su1.payload.signature';

  int calls = 0;
  Map<String, dynamic>? payload;

  Future<http.Response> handle(http.Request request) async {
    calls++;
    payload = Map<String, dynamic>.from(jsonDecode(request.body) as Map);
    return http.Response(
      jsonEncode({'step_up_token': token, 'expires_in': 300}),
      200,
      headers: const {'content-type': 'application/json'},
    );
  }
}
