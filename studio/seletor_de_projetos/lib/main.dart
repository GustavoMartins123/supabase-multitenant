import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'session.dart';
import 'supabase_colors.dart';
import 'project_list_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final r = await http.get(Uri.parse('/api/user/me'));
  if (r.statusCode == 200) {
    final data = jsonDecode(r.body);
    final s = Session();
    s.myId = data['user_id'];
    s.myUsername = data['username'];
    s.myDisplayName = data['display_name'];
    s.isSysAdmin = data['is_admin'];
  }

  runApp(const ProviderScope(child: ProjectInitApp()));
}

class ProjectInitApp extends StatelessWidget {
  const ProjectInitApp({super.key});

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
    home: const ProjectListPage(),
  );
}
