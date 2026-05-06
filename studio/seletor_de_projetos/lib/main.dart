import 'dart:convert';
import 'dart:html' as html;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'bootstrap_admin_page.dart';
import 'session.dart';
import 'supabase_colors.dart';
import 'project_list_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  var needsBootstrapAdmin = false;
  var redirectingToLogin = false;

  final bootstrapResponse = await http.get(Uri.parse('/api/bootstrap/status'));
  if (bootstrapResponse.statusCode == 200) {
    final bootstrapData = jsonDecode(bootstrapResponse.body);
    needsBootstrapAdmin = bootstrapData['needs_admin'] == true;
  }

  if (!needsBootstrapAdmin) {
    final r = await http.get(Uri.parse('/api/user/me'));
    try {
      if (r.statusCode != 200) {
        throw const FormatException('Sessao ausente');
      }
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      final s = Session();
      s.myId = data['user_id'];
      s.myUsername = data['username'];
      s.myDisplayName = data['display_name'];
      s.isSysAdmin = data['is_admin'];
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
      ),
    ),
  );
}

String _loginUrl() {
  final location = html.window.location;
  return '${location.protocol}//${location.hostname}:9091/login';
}

class ProjectInitApp extends StatelessWidget {
  const ProjectInitApp({
    super.key,
    required this.needsBootstrapAdmin,
    required this.redirectingToLogin,
  });

  final bool needsBootstrapAdmin;
  final bool redirectingToLogin;

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
            : redirectingToLogin
                ? const _RedirectingPage()
                : const ProjectListPage(),
      );
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
