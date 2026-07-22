import 'dart:async';
import 'package:web/web.dart' as web;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'admin_users_page.dart';
import 'auth_navigation.dart';
import 'duplicate_project_dialog.dart';
import 'new_project_dialog.dart';
import 'session.dart';
import 'supabase_colors.dart';
import 'providers/config_provider.dart';
import 'providers/favorites_provider.dart';
import 'providers/project_list_provider.dart';
import 'providers/project_jobs_provider.dart';
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

    try {
      final notifier = ref.read(projectListProvider.notifier);
      final ok = await notifier.createProjectAndWait(name);
      if (!mounted) return;
      _snack(
        ok ? 'Projeto criado!' : 'Falhou ao criar',
        ok ? SupabaseColors.success : SupabaseColors.error,
      );
    } catch (error) {
      if (mounted) {
        _snack(
          'Falha ao criar: ${error.toString().replaceFirst('Exception: ', '')}',
          SupabaseColors.error,
        );
      }
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _duplicateAndWait(
    String originalName,
    String newName,
    bool copyData,
  ) async {
    setState(() => _creating = true);
    _snack('Duplicando projeto… aguarde', SupabaseColors.info);

    try {
      final notifier = ref.read(projectListProvider.notifier);
      final ok = await notifier.duplicateProjectAndWait(
        originalName,
        newName,
        copyData,
      );
      if (!mounted) return;
      _snack(
        ok ? 'Projeto duplicado com sucesso!' : 'Falhou ao duplicar',
        ok ? SupabaseColors.success : SupabaseColors.error,
      );
    } catch (error) {
      if (mounted) {
        _snack(
          'Falha ao duplicar: ${error.toString().replaceFirst('Exception: ', '')}',
          SupabaseColors.error,
        );
      }
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _showDuplicateDialog(String originalProjectName) async {
    final Map<String, dynamic>? newProject =
        await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) =>
          DuplicateProjectDialog(originalProjectName: originalProjectName),
    );

    if (!mounted) return;
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
      redirectToLogout();
    }
  }

  void _openProject(String refKey) {
    web.window.open(
      '${web.window.location.origin}/project/$refKey',
      '_blank',
    );
  }

  Future<void> _retryPageLoad() async {
    ref.invalidate(configProvider);
    ref.invalidate(favoritesProvider);
    await Future.wait([
      ref.read(projectListProvider.notifier).refresh(),
      ref.read(projectJobsProvider.notifier).refresh(),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final projectsAsync = ref.watch(projectListProvider);
    final jobsAsync = ref.watch(projectJobsProvider);
    final favoritesAsync = ref.watch(favoritesProvider);
    final configAsync = ref.watch(configProvider);

    ref.listen(projectJobsProvider, (previous, next) {
      final previousIds = previous?.value?.map((job) => job.id).toSet() ?? {};
      final nextIds = next.value?.map((job) => job.id).toSet() ?? {};
      final jobsLoadedForTheFirstTime =
          previous?.isLoading == true && next.hasValue;
      if (jobsLoadedForTheFirstTime ||
          previousIds.difference(nextIds).isNotEmpty) {
        unawaited(ref.read(projectListProvider.notifier).refresh());
      }
    });

    final pageStates = [
      projectsAsync,
      jobsAsync,
      favoritesAsync,
      configAsync,
    ];
    final isLoading = pageStates.any(
      (value) => value.isLoading && !value.hasValue,
    );
    final hasLoadError = pageStates.any((value) => value.hasError);
    final loadError = projectsAsync.error ??
        jobsAsync.error ??
        favoritesAsync.error ??
        configAsync.error;
    final projects = mergeProjectsWithJobs(
      projects: projectsAsync.value ?? [],
      jobs: jobsAsync.value ?? const [],
      currentUserId: Session().myId,
    );
    final favorites = favoritesAsync.value ?? {};
    final serverDomain = configAsync.value?['server_domain'] as String?;
    final hasProjectCreationInFlight = (jobsAsync.value ?? const []).any(
      (job) =>
          job.createdBy == Session().myId &&
          (job.action == 'create' || job.action == 'duplicate'),
    );

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
                      onPressed: _creating || hasProjectCreationInFlight
                          ? null
                          : () async {
                              final name = await showDialog<String>(
                                context: context,
                                builder: (_) => const NewProjectDialog(),
                              );
                              if (!mounted) return;
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
                      if (hasLoadError) {
                        return _buildErrorState(loadError);
                      }
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

  Widget _buildErrorState(Object? error) {
    final message = error
        .toString()
        .replaceFirst('Exception: ', '')
        .replaceFirst('FormatException: ', '');
    return Semantics(
      container: true,
      liveRegion: true,
      label: 'Erro ao carregar projetos: $message',
      child: Padding(
        padding: const EdgeInsets.all(80),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.cloud_off_rounded,
                size: 40,
                color: SupabaseColors.error,
              ),
              const SizedBox(height: 16),
              const Text(
                'Não foi possível carregar os projetos',
                style: TextStyle(
                  color: SupabaseColors.textPrimary,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: SupabaseColors.textMuted,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 18),
              TextButton.icon(
                onPressed: _retryPageLoad,
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
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
    final favProjects =
        projects.where((p) => favorites.contains(p['name'])).toList();
    final otherProjects =
        projects.where((p) => !favorites.contains(p['name'])).toList();

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
                childAspectRatio: 1.35,
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
                childAspectRatio: 1.35,
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
      isLoading: project['is_loading'] == true,
      activeJob: project['active_job'],
      isFavorite: isFavorite,
      serverDomain: serverDomain,
      displayName: project['display_name'] as String?,
      keyExpiresAtEpoch: project['key_expires_at'] as int?,
      keyExpiringSoon: project['key_expiring_soon'] == true,
      keyExpired: project['key_expired'] == true,
      onTap: project['is_loading'] == true || project['active_job'] != null
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
        if (!mounted) return;
        await ref.read(projectListProvider.notifier).refresh();
        await ref.read(projectJobsProvider.notifier).refresh();
      },
      backgroundColor: SupabaseColors.surface300,
      foregroundColor: SupabaseColors.textPrimary,
      elevation: 0,
      icon: const Icon(Icons.admin_panel_settings_rounded, size: 20),
      label: const Text('Admin'),
    );
  }
}
