import 'dart:convert';
import 'dart:html' as html;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/projectSettingsDialog.dart';
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
    s.myId = data['user_id'];
    s.myUsername = data['username'];
    s.myDisplayName = data['display_name'];
    s.isSysAdmin = data['is_admin'];
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

class ProjectListPage extends StatefulWidget {
  const ProjectListPage({super.key});

  @override
  State<ProjectListPage> createState() => _ProjectListPageState();
}

class _ProjectListPageState extends State<ProjectListPage>
    with SingleTickerProviderStateMixin {
  List<Map<String, dynamic>> _projects = [];
  Set<String> _favorites = {};
  String? _serverDomain;
  Future<void>? _loadingFuture;
  bool _creating = false;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _loadingFuture = _initializeData();
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

  Future<void> _initializeData() async {
    await Future.wait([
      _fetchProjects(),
      _fetchConfig(),
      _loadFavorites(),
    ]);
  }

  Future<void> _fetchConfig() async {
    try {
      final r = await http.get(Uri.parse('/api/config'));
      if (r.statusCode == 200) {
        final data = jsonDecode(r.body);
        setState(() {
          _serverDomain = data['server_domain'];
        });
      }
    } catch (_) {}
  }

  Future<void> _loadFavorites() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final favList = prefs.getStringList('project_favorites') ?? [];
      setState(() {
        _favorites = favList.toSet();
      });
    } catch (_) {}
  }

  Future<void> _saveFavorites() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('project_favorites', _favorites.toList());
    } catch (_) {}
  }

  void _toggleFavorite(String projectName) {
    setState(() {
      if (_favorites.contains(projectName)) {
        _favorites.remove(projectName);
      } else {
        _favorites.add(projectName);
      }
    });
    _saveFavorites();
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

  List<Map<String, dynamic>> get _sortedProjects {
    final favs = _projects.where((p) => _favorites.contains(p['name'])).toList();
    final others = _projects.where((p) => !_favorites.contains(p['name'])).toList();
    return [...favs, ...others];
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

    final res = await http.post(
      Uri.parse('/api/projects'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    final job = Job.fromResponse(res);
    if (job == null) {
      setState(() {
        _creating = false;
        _projects.removeWhere((p) => p['is_loading'] == true);
      });
      return;
    }

    _snack('Gerando… aguarde', SupabaseColors.info);
    final ok = await ProjectService.waitUntilReady(job.id);
    setState(() {
      _creating = false;
      _projects.removeWhere((p) => p['is_loading'] == true);
    });

    _snack(
      ok ? 'Projeto criado!' : 'Falhou ao criar',
      ok ? SupabaseColors.success : SupabaseColors.error,
    );
    if (ok) await _fetchProjects();
  }

  void _snack(String msg, [Color? color]) => ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(msg, style: const TextStyle(color: Colors.white)),
      behavior: SnackBarBehavior.floating,
      backgroundColor: color ?? SupabaseColors.surface300,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
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
      await _duplicateAndWait(
        originalProjectName,
        newProject?['name'].trim(),
        newProject?['copy_data'] ?? false,
      );
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
        'copy_data': copyData,
      }),
    );

    final job = Job.fromResponse(res);
    if (job == null) {
      setState(() {
        _creating = false;
        _projects.removeWhere((p) => p['is_loading'] == true);
      });
      _snack('Erro ao duplicar projeto', SupabaseColors.error);
      return;
    }

    _snack('Duplicando projeto… aguarde', SupabaseColors.info);
    final ok = await ProjectService.waitUntilReady(job.id);
    setState(() {
      _creating = false;
      _projects.removeWhere((p) => p['is_loading'] == true);
    });

    _snack(
      ok ? 'Projeto duplicado com sucesso!' : 'Falhou ao duplicar',
      ok ? SupabaseColors.success : SupabaseColors.error,
    );
    if (ok) await _fetchProjects();
  }

  Future<void> _confirmLogout() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: SupabaseColors.surface200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: const Row(
          children: [
            Icon(Icons.logout_rounded, color: SupabaseColors.textSecondary, size: 22),
            SizedBox(width: 12),
            Text('Sair', style: TextStyle(fontSize: 18, color: SupabaseColors.textPrimary)),
          ],
        ),
        content: const Text(
          'Tem certeza que deseja sair?',
          style: TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar', style: TextStyle(color: SupabaseColors.textMuted)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: SupabaseColors.error,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sair'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      html.window.location.href = '/logout';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            floating: true,
            pinned: true,
            expandedHeight: 120,
            backgroundColor: SupabaseColors.bg100,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            flexibleSpace: FlexibleSpaceBar(
              titlePadding: const EdgeInsets.only(left: 24, bottom: 16),
              title: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Meus Projetos',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w600,
                          color: SupabaseColors.textPrimary,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${_projects.length} ${_projects.length == 1 ? 'projeto' : 'projetos'}',
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.normal,
                          color: SupabaseColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            actions: [
              Padding(
                padding: const EdgeInsets.only(right: 16, top: 8),
                child: Row(
                  children: [
                    _SupabaseButton(
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
                      icon: Icons.add,
                      label: 'Novo Projeto',
                    ),
                    SizedBox(width: 12,),
                    _IconBtn(
                      icon: Icons.logout_rounded,
                      tooltip: 'Sair',
                      color: SupabaseColors.textSecondary,
                      onPressed: () => _confirmLogout(),
                    ),
                  ],
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
                        return _buildLoadingState();
                      }

                      if (_projects.isEmpty) {
                        return _buildEmptyState();
                      }

                      return _buildProjectGrid();
                    },
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      floatingActionButton: Session().isSysAdmin ? _buildAdminFab() : null,
    );
  }

  Widget _buildLoadingState() {
    return Padding(
      padding: const EdgeInsets.all(80),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 40,
              height: 40,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SupabaseColors.brand,
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Carregando projetos...',
              style: TextStyle(
                color: SupabaseColors.textSecondary,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Padding(
      padding: const EdgeInsets.all(80),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: SupabaseColors.surface200,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: SupabaseColors.border),
              ),
              child: const Icon(
                Icons.folder_open_rounded,
                size: 36,
                color: SupabaseColors.textMuted,
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Nenhum projeto ainda',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: SupabaseColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Crie seu primeiro projeto para começar',
              style: TextStyle(
                fontSize: 14,
                color: SupabaseColors.textMuted,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProjectGrid() {
    final sorted = _sortedProjects;

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_favorites.isNotEmpty && sorted.any((p) => _favorites.contains(p['name']))) ...[
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 12),
              child: Row(
                children: [
                  Icon(Icons.star_rounded, size: 16, color: SupabaseColors.favorite),
                  const SizedBox(width: 8),
                  const Text(
                    'FAVORITOS',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.2,
                      color: SupabaseColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 380,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: 1.6,
              ),
              itemCount: sorted.where((p) => _favorites.contains(p['name'])).length,
              itemBuilder: (_, i) {
                final favProjects = sorted.where((p) => _favorites.contains(p['name'])).toList();
                return _buildCard(favProjects[i], true);
              },
            ),
            const SizedBox(height: 32),
            const Divider(color: SupabaseColors.border, height: 1),
            const SizedBox(height: 24),
          ],

          if (sorted.any((p) => !_favorites.contains(p['name']))) ...[
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 12),
              child: const Text(
                'TODOS OS PROJETOS',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                  color: SupabaseColors.textMuted,
                ),
              ),
            ),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 380,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: 1.6,
              ),
              itemCount: sorted.where((p) => !_favorites.contains(p['name'])).length,
              itemBuilder: (_, i) {
                final otherProjects = sorted.where((p) => !_favorites.contains(p['name'])).toList();
                return _buildCard(otherProjects[i], false);
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCard(Map<String, dynamic> project, bool isFavorite) {
    return _ProjectCard(
      ref: project['name'] as String,
      anonKey: project['anon_token'] ?? '',
      isLoading: project['is_loading'] == true,
      isFavorite: isFavorite,
      serverDomain: _serverDomain,
      onTap: project['is_loading'] == true ? () {} : () => _openProject(project['name']),
      onDuplicate: () => _showDuplicateDialog(project['name']),
      onToggleFavorite: () => _toggleFavorite(project['name']),
      onDeleted: () {
        setState(() {
          _projects.removeWhere((p) => p['name'] == project['name']);
          _favorites.remove(project['name']);
        });
        _saveFavorites();
      },
    );
  }

  Widget _buildAdminFab() {
    return FloatingActionButton.extended(
      onPressed: () async {
        await Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const AdminUsersPage()),
        );
        await _fetchProjects();
      },
      backgroundColor: SupabaseColors.surface300,
      foregroundColor: SupabaseColors.textPrimary,
      elevation: 0,
      icon: const Icon(Icons.admin_panel_settings_rounded, size: 20),
      label: const Text('Admin'),
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
    required this.onToggleFavorite,
    required this.isFavorite,
    this.serverDomain,
    this.isLoading = false,
  });

  final String ref;
  final String anonKey;
  final String? serverDomain;
  final VoidCallback onTap;
  final VoidCallback onDeleted;
  final VoidCallback onDuplicate;
  final VoidCallback onToggleFavorite;
  final bool isLoading;
  final bool isFavorite;

  @override
  State<_ProjectCard> createState() => _ProjectCardState();
}

class _ProjectCardState extends State<_ProjectCard> with TickerProviderStateMixin {
  bool _hover = false;
  bool _keyVisible = false;
  String? _status;
  bool _statusLoading = true;

  @override
  void initState() {
    super.initState();
    if (!widget.isLoading) {
      _fetchStatus();
    }
  }

  Future<void> _fetchStatus() async {
    try {
      final resp = await http.get(Uri.parse('/api/projects/${widget.ref}/status'));
      if (resp.statusCode == 200 && mounted) {
        final data = jsonDecode(resp.body);
        setState(() {
          _status = data['status'];
          _statusLoading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _statusLoading = false);
      }
    }
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

  String get _projectUrl {
    if (widget.serverDomain == null || widget.serverDomain!.isEmpty) {
      return widget.ref;
    }
    return '${widget.serverDomain}/${widget.ref}';
  }

  @override
  Widget build(BuildContext ctx) {
    if (widget.isLoading) {
      return _buildLoadingCard();
    }

    final isRunning = _status == 'running';

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
          decoration: BoxDecoration(
            color: _hover ? SupabaseColors.surface200 : SupabaseColors.surface100,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: _hover ? SupabaseColors.borderHover : SupabaseColors.border,
              width: 1,
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: SupabaseColors.bg300,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.storage_rounded,
                        color: SupabaseColors.brand,
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),

                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Flexible(
                                child: Text(
                                  widget.ref,
                                  style: const TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                    color: SupabaseColors.textPrimary,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              const SizedBox(width: 8),
                              _buildStatusIndicator(isRunning),
                            ],
                          ),
                          const SizedBox(height: 2),
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  _projectUrl,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    color: SupabaseColors.textMuted,
                                    fontFamily: 'monospace',
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              const SizedBox(width: 4),
                              _IconBtn(
                                icon: Icons.link_rounded,
                                tooltip: 'Copiar URL',
                                onPressed: () {
                                  Clipboard.setData(ClipboardData(text: _projectUrl));
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: const Text('URL copiada!'),
                                      backgroundColor: SupabaseColors.success,
                                      behavior: SnackBarBehavior.floating,
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      margin: const EdgeInsets.all(16),
                                    ),
                                  );
                                },
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),

                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _IconBtn(
                          icon: widget.isFavorite ? Icons.star_rounded : Icons.star_border_rounded,
                          color: widget.isFavorite ? SupabaseColors.favorite : SupabaseColors.textMuted,
                          tooltip: widget.isFavorite ? 'Remover favorito' : 'Favoritar',
                          onPressed: widget.onToggleFavorite,
                        ),
                        PopupMenuButton<String>(
                          icon: const Icon(
                            Icons.more_vert_rounded,
                            color: SupabaseColors.textMuted,
                            size: 18,
                          ),
                          color: SupabaseColors.surface300,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                            side: const BorderSide(color: SupabaseColors.border),
                          ),
                          itemBuilder: (context) => [
                            _buildMenuItem('settings', Icons.settings_rounded, 'Configurações'),
                            _buildMenuItem('duplicate', Icons.copy_rounded, 'Duplicar'),
                          ],
                          onSelected: (value) {
                            if (value == 'settings') _openSettings();
                            if (value == 'duplicate') widget.onDuplicate();
                          },
                        ),
                      ],
                    ),
                  ],
                ),

                const Spacer(),

                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'ANON KEY',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1,
                        color: SupabaseColors.textMuted,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                            decoration: BoxDecoration(
                              color: SupabaseColors.bg300,
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: SupabaseColors.border),
                            ),
                            child: Text(
                              widget.anonKey.isEmpty
                                  ? '—'
                                  : _keyVisible
                                  ? widget.anonKey
                                  : '••••••••••••••••••••••••',
                              style: const TextStyle(
                                fontSize: 11,
                                fontFamily: 'monospace',
                                color: SupabaseColors.textSecondary,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ),
                        const SizedBox(width: 6),
                        _IconBtn(
                          icon: _keyVisible ? Icons.visibility_off_rounded : Icons.visibility_rounded,
                          tooltip: _keyVisible ? 'Ocultar' : 'Mostrar',
                          onPressed: widget.anonKey.isEmpty
                              ? null
                              : () => setState(() => _keyVisible = !_keyVisible),
                        ),
                        _IconBtn(
                          icon: Icons.copy_rounded,
                          tooltip: 'Copiar',
                          onPressed: widget.anonKey.isEmpty
                              ? null
                              : () {
                            Clipboard.setData(ClipboardData(text: widget.anonKey));
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: const Text('Chave copiada!'),
                                backgroundColor: SupabaseColors.success,
                                behavior: SnackBarBehavior.floating,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                margin: const EdgeInsets.all(16),
                              ),
                            );
                          },
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
    );
  }

  Widget _buildStatusIndicator(bool isRunning) {
    if (_statusLoading) {
      return const SizedBox(
        width: 12,
        height: 12,
        child: CircularProgressIndicator(
          strokeWidth: 1.5,
          color: SupabaseColors.textMuted,
        ),
      );
    }

    return Tooltip(
      message: isRunning ? 'Running' : 'Stopped',
      child: Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isRunning ? SupabaseColors.success : SupabaseColors.error,
          boxShadow: [
            BoxShadow(
              color: (isRunning ? SupabaseColors.success : SupabaseColors.error).withOpacity(0.5),
              blurRadius: 6,
              spreadRadius: 1,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingCard() {
    return Container(
      decoration: BoxDecoration(
        color: SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _buildShimmer(40, 40, borderRadius: 8),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildShimmer(120, 16),
                      const SizedBox(height: 6),
                      _buildShimmer(80, 12),
                    ],
                  ),
                ),
              ],
            ),
            const Spacer(),
            _buildShimmer(60, 10),
            const SizedBox(height: 8),
            _buildShimmer(double.infinity, 32),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmer(double width, double height, {double borderRadius = 4}) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.3, end: 0.6),
      duration: const Duration(milliseconds: 800),
      builder: (_, value, __) {
        return Container(
          width: width,
          height: height,
          decoration: BoxDecoration(
            color: SupabaseColors.surface300.withOpacity(value),
            borderRadius: BorderRadius.circular(borderRadius),
          ),
        );
      },
    );
  }

  PopupMenuItem<String> _buildMenuItem(String value, IconData icon, String label) {
    return PopupMenuItem(
      value: value,
      child: Row(
        children: [
          Icon(icon, size: 16, color: SupabaseColors.textSecondary),
          const SizedBox(width: 12),
          Text(label, style: const TextStyle(color: SupabaseColors.textPrimary, fontSize: 13)),
        ],
      ),
    );
  }
}


class _IconBtn extends StatelessWidget {
  const _IconBtn({
    required this.icon,
    required this.tooltip,
    this.onPressed,
    this.color,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Icon(
              icon,
              size: 16,
              color: onPressed == null
                  ? SupabaseColors.textMuted.withOpacity(0.5)
                  : (color ?? SupabaseColors.textMuted),
            ),
          ),
        ),
      ),
    );
  }
}

class _SupabaseButton extends StatefulWidget {
  const _SupabaseButton({
    required this.label,
    required this.icon,
    this.onPressed,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;

  @override
  State<_SupabaseButton> createState() => _SupabaseButtonState();
}

class _SupabaseButtonState extends State<_SupabaseButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          color: widget.onPressed == null
              ? SupabaseColors.surface200
              : _hover
              ? SupabaseColors.brandLight
              : SupabaseColors.brand,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: widget.onPressed,
            borderRadius: BorderRadius.circular(6),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    widget.icon,
                    size: 16,
                    color: widget.onPressed == null
                        ? SupabaseColors.textMuted
                        : SupabaseColors.bg100,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    widget.label,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: widget.onPressed == null
                          ? SupabaseColors.textMuted
                          : SupabaseColors.bg100,
                    ),
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