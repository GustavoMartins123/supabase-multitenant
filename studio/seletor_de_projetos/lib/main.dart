// project_picker.dart
import 'dart:convert';
import 'dart:html' as html;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/projectSettingsDialog.dart';
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';

import 'adminUsersPage.dart';
import 'models/job.dart';
import 'newProjectDialog.dart';


Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final r = await http.get(Uri.parse('/api/user/me'));
  if (r.statusCode == 200) {
    final data = jsonDecode(r.body);
    final s = Session();
    s.myId          = data['user_id'];
    s.myUsername    = data['username'];
    s.myDisplayName = data['display_name'];
    s.isSysAdmin    = data['is_admin'];
  }
  runApp(const ProjectPickerApp());
}



class ProjectPickerApp extends StatelessWidget {
  const ProjectPickerApp({super.key});
  @override
  Widget build(BuildContext ctx) => MaterialApp(
    title: 'Escolha o projeto',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
    home: const ProjectListPage(),
  );
}
class ProjectListPage extends StatefulWidget {
  const ProjectListPage({super.key});
  @override
  State<ProjectListPage> createState() => _ProjectListPageState();
}

class _ProjectListPageState extends State<ProjectListPage> {
  //late Future<List<Map<String, dynamic>>> _projects;
  List<Map<String, dynamic>> _projects = [];
  Future<void>? _loadingFuture;
  bool _creating = false;
  @override
  void initState() {
    super.initState();
    _loadingFuture = _fetchProjects();
  }

  Future<void> _fetchProjects() async {
    try {
      final r = await http.get(Uri.parse('/api/projects'));
      if (r.statusCode == 200) {
        final raw = jsonDecode(r.body) as List;
        setState(() {
          _projects = raw.map((e) => Map<String, dynamic>.from(e)).toList();
        });
      }
    } catch (_) {
      setState(() => _projects = []);
    }
  }
  Future<void> _createAndWait(String name) async {
    setState(() => _creating = true);

    final res = await http.post(Uri.parse('/api/projects'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'name': name}));
    final job = Job.fromResponse(res);
    if (job == null) {
      _snack('Erro ao enfileirar');
      setState(() => _creating = false);
      return;
    }

    _snack('Gerando… aguarde');
    final ok = await ProjectService.waitUntilReady(job.id);
    setState(() => _creating = false);

    _snack(ok ? 'Projeto criado!' : 'Falhou ao criar');
    if (ok) await _fetchProjects();
  }

  void _snack(String msg) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));

  Future<void> _openProject(String ref) async {
    await http.get(Uri.parse('/set-project?ref=$ref'));
    html.window.open('${html.window.location.origin}/project/default', '_blank');
  }


  /*──────────────────────────── UI ────────────────────────────*/

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      backgroundColor: t.colorScheme.surfaceVariant,
      appBar: AppBar(
        title: const Text('Selecione o projeto'),
        actions: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Tooltip(
              message: 'Criar novo projeto',
              child: ElevatedButton.icon(
                onPressed: _creating
                    ? null
                    : () async {
                  final name = await showDialog<String>(
                    context: context,
                    builder: (_) => const NewProjectDialog(),
                  );
                  if (name != null && name.trim().isNotEmpty) {
                    await _createAndWait(name.trim());
                  }
                },
                icon: const Icon(Icons.add),
                label: const Text('Novo'),
              ),
            ),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: FutureBuilder<void>(
            future: _loadingFuture,
            builder: (_, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return const CircularProgressIndicator();
              }
              if (_projects.isEmpty) return const Text('Nenhum projeto');

              return GridView.builder(
                padding: const EdgeInsets.all(24),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: 24,
                  mainAxisSpacing: 24,
                  childAspectRatio: 1.2,
                ),
                itemCount: _projects.length,
                itemBuilder: (_, i) => _ProjectCard(
                  ref:  _projects[i]['name'] as String,
                  anonKey: _projects[i]['anon_token'] ?? '',
                  onTap: () => _openProject( _projects[i]['name']),
                  onDeleted: () {
                    setState(() {
                      _projects.removeAt(i);
                    });
                  },
                ),
              );
            },
          ),
        ),
      ),
      floatingActionButton: Session().isSysAdmin? FloatingActionButton(
          onPressed: () async{
            await Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AdminUsersPage()),
            );
            await _fetchProjects();
          },
          child: const Icon(Icons.manage_accounts)
      )
          : null,

    );
  }
}

/*────────────────────────── card do projeto ───────────────────────────*/

class _ProjectCard extends StatefulWidget {
  const _ProjectCard(
      {required this.ref, required this.anonKey, required this.onTap, required this.onDeleted});
  final String ref;
  final String anonKey;
  final VoidCallback onTap;
  final VoidCallback onDeleted;
  @override
  State<_ProjectCard> createState() => _ProjectCardState();
}

class _ProjectCardState extends State<_ProjectCard> {
  bool _hover = false;

  Future<void> _openSettings() async {
    final deleted = await showDialog<String>(
      context: context,
      builder: (_) => ProjectSettingsDialog(ref: widget.ref, anonKey: widget.anonKey),
    );

    if (deleted == widget.ref) {
      widget.onDeleted();
    }
  }

  @override
  @override
  Widget build(BuildContext ctx) {
    final t = Theme.of(ctx);
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: Card(
          elevation: _hover ? 8 : 2,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          child: AnimatedScale(
            scale: _hover ? 1.04 : 1,
            duration: const Duration(milliseconds: 160),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 12),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Center(
                          child: Text(widget.ref,
                              style: t.textTheme.headlineSmall
                                  ?.copyWith(fontWeight: FontWeight.bold)),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.settings),
                        onPressed: _openSettings,
                        tooltip: 'Configurações do projeto',
                      ),
                    ],
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Flexible(
                        child: SelectableText(
                          widget.anonKey.isEmpty
                              ? '—'
                              : '${widget.anonKey.substring(0, 20)}…',
                          style: t.textTheme.bodySmall,
                          maxLines: 1,
                        ),
                      ),
                    IconButton(
                      tooltip: 'Copiar anon key',
                      icon: const Icon(Icons.copy_all, size: 18),
                      onPressed: widget.anonKey.isEmpty
                          ? null
                          : () {
                        Clipboard.setData(ClipboardData(text: widget.anonKey));
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Chave copiada')),
                        );
                      },
                    )
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
