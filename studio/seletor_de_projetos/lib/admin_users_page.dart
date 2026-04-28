import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'createUserDialog.dart';
import 'providers/admin_users_provider.dart';
import 'session.dart';
import 'supabase_colors.dart';
import 'widgets/admin_users/confirm_dialog_widget.dart';
import 'widgets/admin_users/summary_card.dart';
import 'widgets/admin_users/user_card.dart';
import 'models/user_models.dart';

class AdminUsersPage extends ConsumerStatefulWidget {
  const AdminUsersPage({super.key});

  @override
  ConsumerState<AdminUsersPage> createState() => _AdminUsersPageState();
}

class _AdminUsersPageState extends ConsumerState<AdminUsersPage>
    with SingleTickerProviderStateMixin {
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;
  bool _isToggling = false;

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _fadeController.forward();
    });
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  Future<void> _toggleUserStatus(UserInfo user) async {
    if (_isToggling) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => ConfirmDialog(
        title: user.isActive ? 'Desativar usuário?' : 'Ativar usuário?',
        icon: user.isActive ? Icons.block_rounded : Icons.check_circle_rounded,
        iconColor: user.isActive
            ? SupabaseColors.error
            : SupabaseColors.success,
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InfoRow(
              icon: Icons.person_rounded,
              label: 'Usuário',
              value: user.displayName,
            ),
            const SizedBox(height: 6),
            InfoRow(
              icon: Icons.account_circle_rounded,
              label: 'Login',
              value: user.username,
            ),
            const SizedBox(height: 6),
            InfoRow(
              icon: Icons.email_rounded,
              label: 'Email',
              value: user.emailHint,
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color:
                    (user.isActive
                            ? SupabaseColors.error
                            : SupabaseColors.success)
                        .withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color:
                      (user.isActive
                              ? SupabaseColors.error
                              : SupabaseColors.success)
                          .withValues(alpha: 0.2),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.info_outline_rounded,
                    color: user.isActive
                        ? SupabaseColors.error
                        : SupabaseColors.success,
                    size: 16,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      user.isActive
                          ? 'Desativar removerá o acesso e pode afetar projetos existentes.'
                          : 'Ativar restaurará o acesso do usuário.',
                      style: const TextStyle(
                        fontSize: 12,
                        color: SupabaseColors.textSecondary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        confirmLabel: user.isActive ? 'Desativar' : 'Ativar',
        confirmColor: user.isActive
            ? SupabaseColors.error
            : SupabaseColors.success,
      ),
    );

    if (confirmed != true) return;

    setState(() => _isToggling = true);

    try {
      await ref
          .read(adminUsersProvider.notifier)
          .toggleUserStatus(user.id, user.isActive);

      if (mounted) {
        _showSnack(
          user.isActive
              ? 'Usuário ${user.username} desativado'
              : 'Usuário ${user.username} ativado',
          SupabaseColors.success,
        );
      }
    } catch (e) {
      if (mounted) {
        _showSnack('Erro ao alterar status: $e', SupabaseColors.error);
      }
    } finally {
      if (mounted) setState(() => _isToggling = false);
    }
  }

  Future<void> _showCreateUserDialog() async {
    await showDialog(
      context: context,
      builder: (context) => CreateUserDialog(
        onUserCreated: () {
          ref.read(adminUsersProvider.notifier).refresh();
          _showSnack('Usuário criado com sucesso!', SupabaseColors.success);
        },
      ),
    );
  }

  void _showSnack(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: const TextStyle(color: Colors.white)),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final usersAsync = ref.watch(adminUsersProvider);

    return Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            floating: true,
            pinned: true,
            expandedHeight: 100,
            backgroundColor: SupabaseColors.bg100,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            flexibleSpace: FlexibleSpaceBar(
              titlePadding: const EdgeInsets.only(left: 56, bottom: 16),
              title: const Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Gerenciar Usuários',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                      color: SupabaseColors.textPrimary,
                    ),
                  ),
                  SizedBox(height: 2),
                  Text(
                    'Administração de contas',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.normal,
                      color: SupabaseColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              Padding(
                padding: const EdgeInsets.only(right: 16, top: 8),
                child: IconButton(
                  onPressed: () {
                    // Reset animation on manual refresh
                    _fadeController.reset();
                    _fadeController.forward();
                    ref.read(adminUsersProvider.notifier).refresh();
                  },
                  icon: const Icon(Icons.refresh_rounded, size: 20),
                  tooltip: 'Atualizar lista',
                  style: IconButton.styleFrom(
                    backgroundColor: SupabaseColors.surface200,
                  ),
                ),
              ),
            ],
          ),
          SliverToBoxAdapter(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: usersAsync.when(
                loading: () => _buildLoading(),
                error: (err, stack) => _buildError(err.toString()),
                data: (data) => _buildContent(data),
              ),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showCreateUserDialog,
        backgroundColor: SupabaseColors.brand,
        foregroundColor: SupabaseColors.bg100,
        elevation: 0,
        icon: const Icon(Icons.person_add_rounded, size: 20),
        label: const Text(
          'Novo Usuário',
          style: TextStyle(fontWeight: FontWeight.w500),
        ),
      ),
    );
  }

  Widget _buildLoading() {
    return const Padding(
      padding: EdgeInsets.all(80),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 32,
              height: 32,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SupabaseColors.brand,
              ),
            ),
            SizedBox(height: 16),
            Text(
              'Carregando usuários...',
              style: TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError(String error) {
    return Padding(
      padding: const EdgeInsets.all(40),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: SupabaseColors.error.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(
                Icons.error_outline_rounded,
                size: 40,
                color: SupabaseColors.error,
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Erro ao carregar usuários',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: SupabaseColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              error,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 20),
            TextButton.icon(
              onPressed: () => ref.read(adminUsersProvider.notifier).refresh(),
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Tentar novamente'),
              style: TextButton.styleFrom(
                backgroundColor: SupabaseColors.brand,
                foregroundColor: SupabaseColors.bg100,
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 12,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent(UserListResponse data) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1000),
          child: Column(
            children: [
              _buildSummaryCards(data.summary),
              const SizedBox(height: 24),
              data.users.isEmpty
                  ? _buildEmptyState()
                  : Column(
                      children: data.users
                          .map(
                            (user) => UserCard(
                              user: user,
                              onToggle: () => _toggleUserStatus(user),
                              isLoading: _isToggling,
                              isMe: (user.userUuid ?? user.id) == Session().myId,
                              canToggle:
                                  Session().isSysAdmin &&
                                  (user.userUuid ?? user.id) != Session().myId,
                            ),
                          )
                          .toList(),
                    ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryCards(UserSummary summary) {
    return Row(
      children: [
        Expanded(
          child: SummaryCard(
            icon: Icons.people_rounded,
            label: 'Total',
            value: summary.total.toString(),
            color: SupabaseColors.brand,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: SummaryCard(
            icon: Icons.check_circle_rounded,
            label: 'Ativos',
            value: summary.active.toString(),
            color: SupabaseColors.success,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: SummaryCard(
            icon: Icons.block_rounded,
            label: 'Inativos',
            value: summary.inactive.toString(),
            color: SupabaseColors.error,
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState() {
    return Padding(
      padding: const EdgeInsets.all(40),
      child: Column(
        children: [
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: SupabaseColors.surface200,
              borderRadius: BorderRadius.circular(16),
            ),
            child: const Icon(
              Icons.people_outline_rounded,
              size: 36,
              color: SupabaseColors.textMuted,
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'Nenhum usuário encontrado',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: SupabaseColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}
