import 'data/api_client.dart';
import 'models/user_profile.dart';

class AppBootstrapResult {
  const AppBootstrapResult({
    required this.needsBootstrapAdmin,
    required this.accessDenied,
    this.profile,
  });

  final bool needsBootstrapAdmin;
  final bool accessDenied;
  final UserProfile? profile;
}

Future<AppBootstrapResult> loadAppBootstrap(ApiClient client) async {
  final bootstrapResponse = await client.get(
    Uri.parse('/api/bootstrap/status'),
  );
  if (bootstrapResponse.statusCode != 200) {
    throw ApiException.fromResponse(bootstrapResponse);
  }
  final bootstrapData = decodeJsonObject(
    bootstrapResponse,
    context: 'Inicializacao do Studio',
  );
  if (bootstrapData['needs_admin'] is! bool) {
    throw const ApiException(
      ApiFailureKind.invalidResponse,
      'Inicializacao do Studio: needs_admin ausente ou invalido',
    );
  }

  final needsBootstrapAdmin = bootstrapData['needs_admin'] as bool;
  if (needsBootstrapAdmin) {
    return const AppBootstrapResult(
      needsBootstrapAdmin: true,
      accessDenied: false,
    );
  }

  final profileResponse = await client.get(Uri.parse('/api/user/me'));
  if (profileResponse.statusCode == 403) {
    return const AppBootstrapResult(
      needsBootstrapAdmin: false,
      accessDenied: true,
    );
  }
  if (profileResponse.statusCode != 200) {
    throw ApiException.fromResponse(profileResponse);
  }
  final profileData = decodeJsonObject(
    profileResponse,
    context: 'Perfil da sessao',
  );
  final profile = UserProfile.fromJson(profileData);
  if (profile.userId.isEmpty ||
      profile.username.isEmpty ||
      profile.email.isEmpty ||
      profile.displayName.isEmpty) {
    throw const ApiException(
      ApiFailureKind.invalidResponse,
      'Perfil da sessao incompleto',
    );
  }

  return AppBootstrapResult(
    needsBootstrapAdmin: false,
    accessDenied: false,
    profile: profile,
  );
}
