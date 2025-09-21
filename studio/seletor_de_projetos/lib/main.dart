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
    setState(() {
      _creating = true;
      _projects.add({
        'name': name,
        'anon_token': '',
        'is_loading': true,
      });
    });


    final res = await http.post(Uri.parse('/api/projects'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'name': name}));
    final job = Job.fromResponse(res);
    if (job == null) {
      setState(() {
        _creating = false;
        _projects.removeWhere((p) => p['is_loading'] == true);
      });
      return;
    }

    _snack('Gerando… aguarde');
    final ok = await ProjectService.waitUntilReady(job.id);
    setState(() {
      _creating = false;
      _projects.removeWhere((p) => p['is_loading'] == true);
    });

    _snack(ok ? 'Projeto criado!' : 'Falhou ao criar');
    if (ok) await _fetchProjects();
  }

  void _snack(String msg) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));

  Future<void> _openProject(String ref) async {
    await http.get(Uri.parse('/set-project?ref=$ref'));
    html.window.open('${html.window.location.origin}/project/default', '_blank');
  }


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
                  isLoading: _projects[i]['is_loading'] == true,
                  onTap: _projects[i]['is_loading'] == true ? () {} : () => _openProject( _projects[i]['name']),
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


class _ProjectCard extends StatefulWidget {
  const _ProjectCard(
      {required this.ref, required this.anonKey, required this.onTap, required this.onDeleted, this.isLoading = false});
  final String ref;
  final String anonKey;
  final VoidCallback onTap;
  final VoidCallback onDeleted;
  final bool isLoading;
  @override
  State<_ProjectCard> createState() => _ProjectCardState();
}

class _ProjectCardState extends State<_ProjectCard> with TickerProviderStateMixin{
  bool _hover = false;
  late AnimationController _loadingController;
  late Animation<double> _loadingAnimation;

  @override
  void initState() {
    super.initState();
    if (widget.isLoading) {
      _loadingController = AnimationController(
        duration: const Duration(milliseconds: 1500),
        vsync: this,
      );
      _loadingAnimation = Tween<double>(begin: 0.3, end: 1.0).animate(
        CurvedAnimation(parent: _loadingController, curve: Curves.easeInOut),
      );
      _loadingController.repeat(reverse: true);
    }
  }
  
  @override
  void dispose() {
    if (widget.isLoading) {
      _loadingController.dispose();
    }
    super.dispose();
  }

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
  Widget build(BuildContext ctx) {
    final t = Theme.of(ctx);
    if (widget.isLoading) {
      return AnimatedBuilder(
        animation: _loadingAnimation,
        builder: (context, child) {
          return Opacity(
            opacity: _loadingAnimation.value,
            child: Card(
              elevation: 2,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              child: AnimatedOpacity(
                opacity: 0.5,
                duration: const Duration(milliseconds: 1000),
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
                              child: Container(
                                height: 24,
                                width: 120,
                                decoration: BoxDecoration(
                                  color: Colors.grey[300],
                                  borderRadius: BorderRadius.circular(4),
                                ),
                              ),
                            ),
                          ),
                          Container(
                            height: 24,
                            width: 24,
                            decoration: BoxDecoration(
                              color: Colors.grey[300],
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ],
                      ),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Container(
                              height: 16,
                              width: 100,
                              decoration: BoxDecoration(
                                color: Colors.grey[300],
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            height: 18,
                            width: 18,
                            decoration: BoxDecoration(
                              color: Colors.grey[300],
                              borderRadius: BorderRadius.circular(9),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }
      );
    }

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
