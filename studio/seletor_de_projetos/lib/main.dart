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
import 'duplicateProjectDialog.dart';


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
    theme: ThemeData(
      colorSchemeSeed: const Color(0xFF00D9B8),
      brightness: Brightness.light,
      useMaterial3: true,
    ),
    darkTheme: ThemeData(
      colorSchemeSeed: const Color(0xFF00D9B8),
      brightness: Brightness.dark,
      useMaterial3: true,
    ),
    themeMode: ThemeMode.system,
    home: const ProjectListPage(),
  );
}

class ProjectListPage extends StatefulWidget {
  const ProjectListPage({super.key});
  @override
  State<ProjectListPage> createState() => _ProjectListPageState();
}

class _ProjectListPageState extends State<ProjectListPage> with SingleTickerProviderStateMixin {
  List<Map<String, dynamic>> _projects = [];
  Future<void>? _loadingFuture;
  bool _creating = false;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _loadingFuture = _fetchProjects();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeInOut,
    );
    _fadeController.forward();
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(msg),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ),
      );

  Future<void> _openProject(String ref) async {
    await http.get(Uri.parse('/set-project?ref=$ref'));
    html.window.open('${html.window.location.origin}/project/default', '_blank');
  }

  Future<void> _showDuplicateDialog(String originalProjectName) async {
    final Map<String, dynamic>? newProject = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => DuplicateProjectDialog(originalProjectName: originalProjectName),
    );

    if (newProject?['name'] != null && newProject?['name'].trim().isNotEmpty) {
      await _duplicateAndWait(originalProjectName, newProject?['name'].trim(), newProject?['copy_data'] ?? false);
    }
  }

  Future<void> _duplicateAndWait(String originalName, String newName, bool copyData) async {
    setState(() {
      _creating = true;
      _projects.add({
        'name': newName,
        'anon_token': '',
        'is_loading': true,
      });
    });

    final res = await http.post(
      Uri.parse('/api/projects/duplicate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'original_name': originalName,
        'new_name': newName,
        'copy_data' : copyData
      }),
    );

    final job = Job.fromResponse(res);
    if (job == null) {
      setState(() {
        _creating = false;
        _projects.removeWhere((p) => p['is_loading'] == true);
      });
      _snack('Erro ao duplicar projeto');
      return;
    }

    _snack('Duplicando projeto… aguarde');
    final ok = await ProjectService.waitUntilReady(job.id);
    setState(() {
      _creating = false;
      _projects.removeWhere((p) => p['is_loading'] == true);
    });

    _snack(ok ? 'Projeto duplicado com sucesso!' : 'Falhou ao duplicar');
    if (ok) await _fetchProjects();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? const Color(0xFF0A0E1A) : const Color(0xFFF5F7FA),
      body: CustomScrollView(
        slivers: [
          SliverAppBar.large(
            floating: true,
            pinned: true,
            backgroundColor: isDark ? const Color(0xFF0F1419) : Colors.white,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            flexibleSpace: FlexibleSpaceBar(
              titlePadding: const EdgeInsets.only(left: 24, bottom: 16),
              title: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Meus Projetos',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.white : Colors.black87,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${_projects.length} ${_projects.length == 1 ? 'projeto' : 'projetos'}',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.normal,
                      color: isDark ? Colors.white54 : Colors.black45,
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              Padding(
                padding: const EdgeInsets.only(right: 16, top: 8),
                child: FilledButton.tonalIcon(
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
                  icon: const Icon(Icons.add_rounded, size: 20),
                  label: const Text('Novo Projeto'),
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                ),
              ),
            ],
          ),
          SliverToBoxAdapter(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1400),
                  child: FutureBuilder<void>(
                    future: _loadingFuture,
                    builder: (_, snap) {
                      if (snap.connectionState != ConnectionState.done) {
                        return Padding(
                          padding: const EdgeInsets.all(80),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                SizedBox(
                                  width: 50,
                                  height: 50,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 3,
                                    color: t.colorScheme.primary,
                                  ),
                                ),
                                const SizedBox(height: 24),
                                Text(
                                  'Carregando projetos...',
                                  style: TextStyle(
                                    color: isDark ? Colors.white70 : Colors.black54,
                                    fontSize: 15,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }

                      if (_projects.isEmpty) {
                        return Padding(
                          padding: const EdgeInsets.all(80),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 120,
                                  height: 120,
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      colors: [
                                        t.colorScheme.primary.withOpacity(0.2),
                                        t.colorScheme.secondary.withOpacity(0.1),
                                      ],
                                    ),
                                    shape: BoxShape.circle,
                                  ),
                                  child: Icon(
                                    Icons.folder_open_rounded,
                                    size: 56,
                                    color: t.colorScheme.primary,
                                  ),
                                ),
                                const SizedBox(height: 32),
                                Text(
                                  'Nenhum projeto ainda',
                                  style: TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.bold,
                                    color: isDark ? Colors.white : Colors.black87,
                                  ),
                                ),
                                const SizedBox(height: 12),
                                Text(
                                  'Crie seu primeiro projeto para começar',
                                  style: TextStyle(
                                    fontSize: 15,
                                    color: isDark ? Colors.white60 : Colors.black54,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }

                      return GridView.builder(
                        padding: const EdgeInsets.all(24),
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 420,
                          crossAxisSpacing: 20,
                          mainAxisSpacing: 20,
                          childAspectRatio: 1.35,
                        ),
                        itemCount: _projects.length,
                        itemBuilder: (_, i) => _ProjectCard(
                          ref: _projects[i]['name'] as String,
                          anonKey: _projects[i]['anon_token'] ?? '',
                          isLoading: _projects[i]['is_loading'] == true,
                          onTap: _projects[i]['is_loading'] == true
                              ? () {}
                              : () => _openProject(_projects[i]['name']),
                          onDuplicate: ()=> _showDuplicateDialog(_projects[i]['name']),
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
            ),
          ),
        ],
      ),
      floatingActionButton: Session().isSysAdmin
          ? Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              t.colorScheme.primary,
              t.colorScheme.secondary,
            ],
          ),
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: t.colorScheme.primary.withOpacity(0.4),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: FloatingActionButton.extended(
          onPressed: () async {
            await Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AdminUsersPage()),
            );
            await _fetchProjects();
          },
          backgroundColor: Colors.transparent,
          elevation: 0,
          icon: const Icon(Icons.admin_panel_settings_rounded),
          label: const Text('Admin'),
        ),
      )
          : null,
    );
  }
}


class _ProjectCard extends StatefulWidget {
  const _ProjectCard({
    required this.ref,
    required this.anonKey,
    required this.onTap,
    required this.onDeleted,
    required this.onDuplicate,
    this.isLoading = false,
  });

  final String ref;
  final String anonKey;
  final VoidCallback onTap;
  final VoidCallback onDeleted;
  final VoidCallback onDuplicate;
  final bool isLoading;

  @override
  State<_ProjectCard> createState() => _ProjectCardState();
}

class _ProjectCardState extends State<_ProjectCard> with TickerProviderStateMixin {
  bool _hover = false;
  late AnimationController _loadingController;
  late Animation<double> _loadingAnimation;
  late AnimationController _shimmerController;

  @override
  void initState() {
    super.initState();
    if (widget.isLoading) {
      _loadingController = AnimationController(
        duration: const Duration(milliseconds: 1500),
        vsync: this,
      );
      _loadingAnimation = Tween<double>(begin: 0.4, end: 1.0).animate(
        CurvedAnimation(parent: _loadingController, curve: Curves.easeInOut),
      );
      _loadingController.repeat(reverse: true);

      _shimmerController = AnimationController(
        duration: const Duration(milliseconds: 2000),
        vsync: this,
      )..repeat();
    }
  }

  @override
  void dispose() {
    if (widget.isLoading) {
      _loadingController.dispose();
      _shimmerController.dispose();
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
    final isDark = t.brightness == Brightness.dark;

    if (widget.isLoading) {
      return AnimatedBuilder(
        animation: _loadingAnimation,
        builder: (context, child) {
          return Opacity(
            opacity: _loadingAnimation.value,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(24),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: isDark
                      ? [
                    const Color(0xFF1A1F2E),
                    const Color(0xFF12161F),
                  ]
                      : [
                    Colors.white,
                    Colors.grey[50]!,
                  ],
                ),
                border: Border.all(
                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08),
                  width: 1,
                ),
              ),
              child: Stack(
                children: [
                  AnimatedBuilder(
                    animation: _shimmerController,
                    builder: (_, __) {
                      return Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(24),
                          gradient: LinearGradient(
                            begin: Alignment(-1.0 + (_shimmerController.value * 2), 0),
                            end: Alignment(1.0 + (_shimmerController.value * 2), 0),
                            colors: [
                              Colors.transparent,
                              Colors.white.withOpacity(isDark ? 0.05 : 0.2),
                              Colors.transparent,
                            ],
                            stops: const [0.0, 0.5, 1.0],
                          ),
                        ),
                      );
                    },
                  ),
                  Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 150,
                              height: 28,
                              decoration: BoxDecoration(
                                color: isDark ? Colors.white.withOpacity(0.1) : Colors.grey[300],
                                borderRadius: BorderRadius.circular(8),
                              ),
                            ),
                            const Spacer(),
                            Container(
                              width: 32,
                              height: 32,
                              decoration: BoxDecoration(
                                color: isDark ? Colors.white.withOpacity(0.1) : Colors.grey[300],
                                borderRadius: BorderRadius.circular(8),
                              ),
                            ),
                          ],
                        ),
                        Container(
                          width: 120,
                          height: 16,
                          decoration: BoxDecoration(
                            color: isDark ? Colors.white.withOpacity(0.06) : Colors.grey[200],
                            borderRadius: BorderRadius.circular(6),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      );
    }

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            gradient: _hover
                ? LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                t.colorScheme.primary.withOpacity(0.15),
                t.colorScheme.secondary.withOpacity(0.1),
              ],
            )
                : LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: isDark
                  ? [
                const Color(0xFF1A1F2E),
                const Color(0xFF12161F),
              ]
                  : [
                Colors.white,
                Colors.grey[50]!,
              ],
            ),
            border: Border.all(
              color: _hover
                  ? t.colorScheme.primary.withOpacity(0.4)
                  : (isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08)),
              width: 1.5,
            ),
            boxShadow: _hover
                ? [
              BoxShadow(
                color: t.colorScheme.primary.withOpacity(0.2),
                blurRadius: 24,
                offset: const Offset(0, 12),
              ),
            ]
                : [
              BoxShadow(
                color: isDark ? Colors.black.withOpacity(0.3) : Colors.black.withOpacity(0.08),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: AnimatedScale(
            scale: _hover ? 1.02 : 1.0,
            duration: const Duration(milliseconds: 250),
            curve: Curves.easeOut,
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              t.colorScheme.primary.withOpacity(0.2),
                              t.colorScheme.secondary.withOpacity(0.2),
                            ],
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(
                          Icons.folder_rounded,
                          color: t.colorScheme.primary,
                          size: 24,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          widget.ref,
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                            color: isDark ? Colors.white : Colors.black87,
                            letterSpacing: -0.3,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        decoration: BoxDecoration(
                          color: isDark
                              ? Colors.white.withOpacity(0.05)
                              : Colors.black.withOpacity(0.03),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: PopupMenuButton<String>(
                          icon: Icon(
                            Icons.more_vert_rounded,
                            color: isDark ? Colors.white70 : Colors.black54,
                            size: 20,
                          ),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                          itemBuilder: (context) => [
                            PopupMenuItem(
                              value: 'settings',
                              child: Row(
                                children: [
                                  Icon(
                                    Icons.settings_rounded,
                                    size: 18,
                                    color: isDark ? Colors.white70 : Colors.black54,
                                  ),
                                  const SizedBox(width: 12),
                                  const Text('Configurações'),
                                ],
                              ),
                            ),
                            PopupMenuItem(
                              value: 'duplicate',
                              child: Row(
                                children: [
                                  Icon(
                                    Icons.content_copy_rounded,
                                    size: 18,
                                    color: t.colorScheme.primary,
                                  ),
                                  const SizedBox(width: 12),
                                  Text(
                                    'Duplicar projeto',
                                    style: TextStyle(color: t.colorScheme.primary),
                                  ),
                                ],
                              ),
                            ),
                          ],
                          onSelected: (value) {
                            if (value == 'settings') {
                              _openSettings();
                            } else if (value == 'duplicate') {
                              widget.onDuplicate();
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'CHAVE ANÔNIMA',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1.2,
                          color: isDark ? Colors.white38 : Colors.black38,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                              decoration: BoxDecoration(
                                color: isDark
                                    ? Colors.black.withOpacity(0.3)
                                    : Colors.grey[200],
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: isDark
                                      ? Colors.white.withOpacity(0.05)
                                      : Colors.black.withOpacity(0.05),
                                ),
                              ),
                              child: SelectableText(
                                widget.anonKey.isEmpty
                                    ? '—'
                                    : '${widget.anonKey.substring(0, 20)}…',
                                style: TextStyle(
                                  fontSize: 12,
                                  fontFamily: 'monospace',
                                  color: isDark ? Colors.white60 : Colors.black54,
                                ),
                                maxLines: 1,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            decoration: BoxDecoration(
                              color: widget.anonKey.isEmpty
                                  ? (isDark ? Colors.white.withOpacity(0.05) : Colors.grey[200])
                                  : t.colorScheme.primary.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: IconButton(
                              tooltip: 'Copiar chave',
                              icon: Icon(
                                Icons.copy_all_rounded,
                                size: 18,
                                color: widget.anonKey.isEmpty
                                    ? (isDark ? Colors.white24 : Colors.black26)
                                    : t.colorScheme.primary,
                              ),
                              onPressed: widget.anonKey.isEmpty
                                  ? null
                                  : () {
                                Clipboard.setData(ClipboardData(text: widget.anonKey));
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: const Text('Chave copiada'),
                                    behavior: SnackBarBehavior.floating,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    margin: const EdgeInsets.all(16),
                                  ),
                                );
                              },
                            ),
                          ),
                        ],
                      ),
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
