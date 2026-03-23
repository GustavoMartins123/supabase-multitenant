import 'dart:html' as html;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'admin_users_page.dart';
import 'duplicateProjectDialog.dart';
import 'newProjectDialog.dart';
import 'session.dart';
import 'supabase_colors.dart';
import 'providers/config_provider.dart';
import 'providers/favorites_provider.dart';
import 'providers/project_list_provider.dart';
import 'widgets/project_card.dart';
import 'widgets/supabase_button.dart';

class ProjectListPage extends ConsumerStatefulWidget {
  const ProjectListPage({super.key});

  @override
  ConsumerState<ProjectListPage> createState() => _ProjectListPageState();
}

class _ProjectListPageState extends ConsumerState<ProjectListPage>
    with SingleTickerProviderStateMixin {
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;
  bool _creating = false;

  @override
  void initState() {
    super.initState();
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

  void _snack(String msg, [Color? color]) =>
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(msg, style: const TextStyle(color: Colors.white)),
          behavior: SnackBarBehavior.floating,
          backgroundColor: color ?? SupabaseColors.surface300,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          margin: const EdgeInsets.all(16),
        ),
      );

  Future<void> _createAndWait(String name) async {
    setState(() => _creating = true);
    _snack('Gerando… aguarde', SupabaseColors.info);

    final notifier = ref.read(projectListProvider.notifier);
    final ok = await notifier.createProjectAndWait(name);

    setState(() => _creating = false);
    _snack(
      ok ? 'Projeto criado!' : 'Falhou ao criar',
      ok ? SupabaseColors.success : SupabaseColors.error,
    );
  }

  Future<void> _duplicateAndWait(
    String originalName,
    String newName,
    bool copyData,
  ) async {
    setState(() => _creating = true);
    _snack('Duplicando projeto… aguarde', SupabaseColors.info);

    final notifier = ref.read(projectListProvider.notifier);
    final ok = await notifier.duplicateProjectAndWait(
      originalName,
      newName,
      copyData,
    );

    setState(() => _creating = false);
    _snack(
      ok ? 'Projeto duplicado com sucesso!' : 'Falhou ao duplicar',
      ok ? SupabaseColors.success : SupabaseColors.error,
    );
  }

  Future<void> _showDuplicateDialog(String originalProjectName) async {
    final Map<String, dynamic>? newProject =
        await showDialog<Map<String, dynamic>>(
          context: context,
          builder: (_) =>
              DuplicateProjectDialog(originalProjectName: originalProjectName),
        );

    if (newProject?['name'] != null && newProject?['name'].trim().isNotEmpty) {
      await _duplicateAndWait(
        originalProjectName,
        newProject?['name'].trim(),
        newProject?['copy_data'] ?? false,
      );
    }
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
            Icon(
              Icons.logout_rounded,
              color: SupabaseColors.textSecondary,
              size: 22,
            ),
            SizedBox(width: 12),
            Text(
              'Sair',
              style: TextStyle(fontSize: 18, color: SupabaseColors.textPrimary),
            ),
          ],
        ),
        content: const Text(
          'Tem certeza que deseja sair?',
          style: TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text(
              'Cancelar',
              style: TextStyle(color: SupabaseColors.textMuted),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: SupabaseColors.error,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(6),
              ),
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

  Future<void> _openProject(String refKey) async {
    await http.get(Uri.parse('/set-project?ref=$refKey'));
    html.window.open(
      '${html.window.location.origin}/project/default',
      '_blank',
    );
  }

  @override
  Widget build(BuildContext context) {
    final projectsAsync = ref.watch(projectListProvider);
    final favoritesAsync = ref.watch(favoritesProvider);
    final configAsync = ref.watch(configProvider);

    final isLoading = projectsAsync.isLoading && !projectsAsync.hasValue;
    final projects = projectsAsync.value ?? [];
    final favorites = favoritesAsync.value ?? {};
    final serverDomain = configAsync.value?['server_domain'] as String?;

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
                      if (!isLoading)
                        Text(
                          '${projects.length} ${projects.length == 1 ? 'projeto' : 'projetos'}',
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
                    SupabaseButton(
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
                    const SizedBox(width: 12),
                    IconBtn(
                      icon: Icons.logout_rounded,
                      tooltip: 'Sair',
                      color: SupabaseColors.textSecondary,
                      onPressed: _confirmLogout,
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
                  child: Builder(
                    builder: (_) {
                      if (isLoading) return _buildLoadingState();
                      if (projects.isEmpty) return _buildEmptyState();

                      return _buildProjectGrid(
                        projects,
                        favorites,
                        serverDomain,
                      );
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
            const SizedBox(
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
              style: TextStyle(fontSize: 14, color: SupabaseColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProjectGrid(
    List<Map<String, dynamic>> projects,
    Set<String> favorites,
    String? serverDomain,
  ) {
    final favProjects = projects
        .where((p) => favorites.contains(p['name']))
        .toList();
    final otherProjects = projects
        .where((p) => !favorites.contains(p['name']))
        .toList();

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (favProjects.isNotEmpty) ...[
            const Padding(
              padding: EdgeInsets.only(left: 4, bottom: 12),
              child: Row(
                children: [
                  Icon(
                    Icons.star_rounded,
                    size: 16,
                    color: SupabaseColors.favorite,
                  ),
                  SizedBox(width: 8),
                  Text(
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
              itemCount: favProjects.length,
              itemBuilder: (_, i) =>
                  _buildCard(favProjects[i], true, serverDomain),
            ),
            const SizedBox(height: 32),
            const Divider(color: SupabaseColors.border, height: 1),
            const SizedBox(height: 24),
          ],
          if (otherProjects.isNotEmpty) ...[
            const Padding(
              padding: EdgeInsets.only(left: 4, bottom: 12),
              child: Text(
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
              itemCount: otherProjects.length,
              itemBuilder: (_, i) =>
                  _buildCard(otherProjects[i], false, serverDomain),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCard(
    Map<String, dynamic> project,
    bool isFavorite,
    String? serverDomain,
  ) {
    return ProjectCard(
      refKey: project['name'] as String,
      anonKey: project['anon_token'] ?? '',
      configToken: project['config_token'] ?? '',
      isLoading: project['is_loading'] == true,
      isFavorite: isFavorite,
      serverDomain: serverDomain,
      onTap: project['is_loading'] == true
          ? () {}
          : () => _openProject(project['name']),
      onDuplicate: () => _showDuplicateDialog(project['name']),
      onToggleFavorite: () =>
          ref.read(favoritesProvider.notifier).toggleFavorite(project['name']),
      onDeleted: () {
        ref
            .read(projectListProvider.notifier)
            .removeProjectLocal(project['name']);
        ref.read(favoritesProvider.notifier).removeFavorite(project['name']);
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
        ref.invalidate(projectListProvider);
      },
      backgroundColor: SupabaseColors.surface300,
      foregroundColor: SupabaseColors.textPrimary,
      elevation: 0,
      icon: const Icon(Icons.admin_panel_settings_rounded, size: 20),
      label: const Text('Admin'),
    );
  }
}
