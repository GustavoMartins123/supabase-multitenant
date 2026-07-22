import 'dart:convert';
import 'package:web/web.dart' as web;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'bootstrap_admin_page.dart';
import 'data/api_client.dart';
import 'models/user_profile.dart';
import 'project_list_page.dart';
import 'session.dart';
import 'supabase_colors.dart';
import 'user_profile_dialog.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  var needsBootstrapAdmin = false;
  var redirectingToLogin = false;
  var accessDenied = false;
  String? initializationError;
  final client = ApiClient();

  try {
    final bootstrapResponse = await client.get(
      Uri.parse('/api/bootstrap/status'),
    );
    if (bootstrapResponse.statusCode != 200) {
      throw ApiException.fromResponse(bootstrapResponse);
    }
    final bootstrapData = jsonDecode(bootstrapResponse.body);
    if (bootstrapData is! Map) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta de inicializacao invalida',
      );
    }
    needsBootstrapAdmin = bootstrapData['needs_admin'] == true;

    if (!needsBootstrapAdmin) {
      final response = await client.get(Uri.parse('/api/user/me'));
      if (response.statusCode == 403) {
        accessDenied = true;
      } else if (response.statusCode == 401) {
        redirectingToLogin = true;
        web.window.location.href = _loginUrl();
      } else if (response.statusCode != 200) {
        throw ApiException.fromResponse(response);
      } else {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        Session().setProfile(UserProfile.fromJson(data));
      }
    }
  } catch (error) {
    initializationError = error.toString();
  } finally {
    client.close();
  }

  runApp(
    ProviderScope(
      child: ProjectInitApp(
        needsBootstrapAdmin: needsBootstrapAdmin,
        redirectingToLogin: redirectingToLogin,
        accessDenied: accessDenied,
        initializationError: initializationError,
      ),
    ),
  );
}

String _loginUrl() {
  final location = web.window.location;
  return '${location.protocol}//${location.hostname}:9091/login';
}

String _logoutUrl() {
  final location = web.window.location;
  return '${location.protocol}//${location.hostname}:9091/logout';
}

class ProjectInitApp extends StatelessWidget {
  const ProjectInitApp({
    super.key,
    required this.needsBootstrapAdmin,
    required this.redirectingToLogin,
    required this.accessDenied,
    required this.initializationError,
  });

  final bool needsBootstrapAdmin;
  final bool redirectingToLogin;
  final bool accessDenied;
  final String? initializationError;

  @override
  Widget build(BuildContext ctx) => MaterialApp(
        title: 'Escolha o projeto',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorSchemeSeed: SupabaseColors.brand,
          brightness: Brightness.dark,
          useMaterial3: true,
          scaffoldBackgroundColor: SupabaseColors.bg100,
          cardColor: SupabaseColors.surface100,
          dividerColor: SupabaseColors.border,
        ),
        darkTheme: ThemeData(
          colorSchemeSeed: SupabaseColors.brand,
          brightness: Brightness.dark,
          useMaterial3: true,
          scaffoldBackgroundColor: SupabaseColors.bg100,
          cardColor: SupabaseColors.surface100,
          dividerColor: SupabaseColors.border,
        ),
        themeMode: ThemeMode.dark,
        home: initializationError != null
            ? _InitializationErrorPage(message: initializationError!)
            : needsBootstrapAdmin
                ? const BootstrapAdminPage()
                : accessDenied
                    ? const _AccessDeniedPage()
                    : redirectingToLogin
                        ? const _RedirectingPage()
                        : const Stack(
                            fit: StackFit.expand,
                            children: [
                              ProjectListPage(),
                              Positioned(
                                left: 24,
                                bottom: 24,
                                child: UserProfileLauncher(),
                              ),
                            ],
                          ),
      );
}

class _InitializationErrorPage extends StatelessWidget {
  const _InitializationErrorPage({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: Center(
        child: Semantics(
          liveRegion: true,
          label: 'Falha ao iniciar o Studio: $message',
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.cloud_off_rounded,
                  color: SupabaseColors.error,
                  size: 36,
                ),
                const SizedBox(height: 16),
                const Text(
                  'Falha ao iniciar o Studio',
                  style: TextStyle(
                    color: SupabaseColors.textPrimary,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: SupabaseColors.textSecondary),
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: web.window.location.reload,
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Tentar novamente'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AccessDeniedPage extends StatelessWidget {
  const _AccessDeniedPage();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: Center(
        child: Container(
          width: 420,
          margin: const EdgeInsets.all(24),
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: SupabaseColors.bg200,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: SupabaseColors.border),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(
                Icons.lock_outline_rounded,
                color: SupabaseColors.warning,
                size: 34,
              ),
              const SizedBox(height: 16),
              const Text(
                'Acesso negado',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: SupabaseColors.textPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                'Sua conta não tem permissão para acessar o Studio.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: SupabaseColors.textSecondary,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 22),
              ElevatedButton.icon(
                onPressed: () {
                  web.window.location.href = _logoutUrl();
                },
                icon: const Icon(Icons.logout_rounded, size: 18),
                label: const Text('Sair'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: SupabaseColors.brand,
                  foregroundColor: SupabaseColors.bg100,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RedirectingPage extends StatelessWidget {
  const _RedirectingPage();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: Center(
        child: SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: SupabaseColors.brand,
          ),
        ),
      ),
    );
  }
}
