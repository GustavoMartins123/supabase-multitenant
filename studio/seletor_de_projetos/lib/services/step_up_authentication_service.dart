import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/api_client.dart';

enum StepUpAction {
  deleteProject('delete_project'),
  revealSecretKey('reveal_secret_key'),
  createSecretKey('create_secret_key'),
  rotateSecretKey('rotate_secret_key');

  const StepUpAction(this.wireValue);

  final String wireValue;
}

typedef StepUpTokenRequester = Future<String> Function({
  required String password,
  required StepUpAction action,
  required String projectRef,
  required String resourceId,
});

final stepUpAuthenticationServiceProvider =
    Provider<StepUpAuthenticationService>((ref) {
  final service = StepUpAuthenticationService();
  ref.onDispose(service.close);
  return service;
});

final class StepUpAuthenticationService {
  StepUpAuthenticationService({ApiClient? client})
      : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<String> requestToken({
    required String password,
    required StepUpAction action,
    required String projectRef,
    required String resourceId,
  }) async {
    if (password.isEmpty) {
      throw const ApiException(
        ApiFailureKind.validation,
        'Digite a senha da sua conta.',
      );
    }
    final response = await _client.post(
      Uri.parse('/api/security/step-up'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'password': password,
        'action': action.wireValue,
        'project': projectRef,
        'resource': resourceId,
      }),
    );
    if (response.statusCode != 200) {
      throw ApiException.fromResponse(response);
    }

    final payload = decodeJsonObject(
      response,
      context: 'Reautenticacao',
    );
    final token = payload['step_up_token'];
    final expiresIn = payload['expires_in'];
    if (token is! String ||
        !token.startsWith('su1.') ||
        expiresIn is! int ||
        expiresIn <= 0 ||
        expiresIn > 300) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta de reautenticacao invalida.',
      );
    }
    return token;
  }

  void close() => _client.close();
}
