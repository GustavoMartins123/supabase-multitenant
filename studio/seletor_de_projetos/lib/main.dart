import 'dart:convert';
import 'dart:html' as html;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'bootstrap_admin_page.dart';
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

  final bootstrapResponse = await http.get(Uri.parse('/api/bootstrap/status'));
  if (bootstrapResponse.statusCode == 200) {
    final bootstrapData = jsonDecode(bootstrapResponse.body);
    needsBootstrapAdmin = bootstrapData['needs_admin'] == true;
  }

  if (!needsBootstrapAdmin) {
    final response = await http.get(Uri.parse('/api/user/me'));
    try {
      if (response.statusCode == 403) {
        accessDenied = true;
        throw const _AccessDeniedException();
      }
      if (response.statusCode != 200) {
        throw const FormatException('Sessao ausente');
      }
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      Session().setProfile(UserProfile.fromJson(data));
    } on _AccessDeniedException {
    } on FormatException {
      redirectingToLogin = true;
      html.window.location.href = _loginUrl();
    }
  }

  runApp(
    ProviderScope(
      child: ProjectInitApp(
        needsBootstrapAdmin: needsBootstrapAdmin,
        redirectingToLogin: redirectingToLogin,
        accessDenied: accessDenied,
      ),
    ),
  );
}

String _loginUrl() {
  final location = html.window.location;
  return '${location.protocol}//${location.hostname}:9091/login';
}

String _logoutUrl() {
  final location = html.window.location;
  return '${location.protocol}//${location.hostname}:9091/logout';
}

class _AccessDeniedException implements Exception {
  const _AccessDeniedException();
}

class ProjectInitApp extends StatelessWidget {
  const ProjectInitApp({
    super.key,
    required this.needsBootstrapAdmin,
    required this.redirectingToLogin,
    required this.accessDenied,
  });

  final bool needsBootstrapAdmin;
  final bool redirectingToLogin;
  final bool accessDenied;

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
        home: needsBootstrapAdmin
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
                  html.window.location.href = _logoutUrl();
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
