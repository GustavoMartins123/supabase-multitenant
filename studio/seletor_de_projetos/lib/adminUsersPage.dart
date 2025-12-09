import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/session.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';
import 'package:seletor_de_projetos/userProjectsAdminScreen.dart';
import 'createUserDialog.dart';

class AdminUsersPage extends StatefulWidget {
  const AdminUsersPage({super.key});

  @override
  State<AdminUsersPage> createState() => _AdminUsersPageState();
}

class _AdminUsersPageState extends State<AdminUsersPage>
    with SingleTickerProviderStateMixin {
  late Future<UserListResponse> _usersFuture;
  bool _isLoading = false;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _refreshUsers();

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    );
    _fadeController.forward();
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  void _refreshUsers() {
    setState(() {
      _usersFuture = _fetchUsers();
    });
  }

  Future<UserListResponse> _fetchUsers() async {
    try {
      final response = await http.get(Uri.parse('/api/admin/users'));

      if (response.statusCode == 403) {
        throw Exception('Acesso negado - apenas administradores');
      }

      if (response.statusCode != 200) {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }

      if (response.body.isEmpty) {
        throw Exception('Resposta vazia da API');
      }

      final data = jsonDecode(response.body);
      if (data == null) {
        throw Exception('Dados inválidos retornados pela API');
      }

      final resp = UserListResponse.fromJson(data);

      if (resp.users.isNotEmpty) {
        final session = Session();
        resp.users.sort((a, b) {
          if (a.id == session.myId) return -1;
          if (b.id == session.myId) return 1;
          return 0;
        });
      }

      return resp;
    } catch (e) {
      throw Exception('Erro ao carregar usuários: $e');
    }
  }

  Future<void> _toggleUserStatus(UserInfo user) async {
    if (_isLoading) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => _ConfirmDialog(
        title: user.isActive ? 'Desativar usuário?' : 'Ativar usuário?',
        icon: user.isActive ? Icons.block_rounded : Icons.check_circle_rounded,
        iconColor: user.isActive ? SupabaseColors.error : SupabaseColors.success,
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _InfoRow(icon: Icons.person_rounded, label: 'Usuário', value: user.displayName),
            const SizedBox(height: 6),
            _InfoRow(icon: Icons.account_circle_rounded, label: 'Login', value: user.username),
            const SizedBox(height: 6),
            _InfoRow(icon: Icons.email_rounded, label: 'Email', value: user.emailHint),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: (user.isActive ? SupabaseColors.error : SupabaseColors.success).withOpacity(0.1),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color: (user.isActive ? SupabaseColors.error : SupabaseColors.success).withOpacity(0.2),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.info_outline_rounded,
                    color: user.isActive ? SupabaseColors.error : SupabaseColors.success,
                    size: 16,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      user.isActive
                          ? 'Desativar removerá o acesso e pode afetar projetos existentes.'
                          : 'Ativar restaurará o acesso do usuário.',
                      style: const TextStyle(fontSize: 12, color: SupabaseColors.textSecondary),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        confirmLabel: user.isActive ? 'Desativar' : 'Ativar',
        confirmColor: user.isActive ? SupabaseColors.error : SupabaseColors.success,
      ),
    );

    if (confirmed != true) return;

    setState(() => _isLoading = true);

    try {
      final endpoint = user.isActive ? 'deactivate' : 'activate';
      final response = await http.post(
        Uri.parse('/api/admin/users/${user.id}/$endpoint'),
        headers: {'Content-Type': 'application/json'},
      );

      if (response.statusCode == 200) {
        _showSnack(
          user.isActive
              ? 'Usuário ${user.username} desativado'
              : 'Usuário ${user.username} ativado',
          SupabaseColors.success,
        );
        _refreshUsers();
      } else {
        final error = jsonDecode(response.body)['error'] ?? 'Erro desconhecido';
        _showSnack('Erro: $error', SupabaseColors.error);
      }
    } catch (e) {
      _showSnack('Erro: $e', SupabaseColors.error);
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _showCreateUserDialog() async {
    await showDialog(
      context: context,
      builder: (context) => CreateUserDialog(
        onUserCreated: () {
          _refreshUsers();
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
                  onPressed: _refreshUsers,
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
              child: FutureBuilder<UserListResponse>(
                future: _usersFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return _buildLoading();
                  }

                  if (snapshot.hasError) {
                    return _buildError(snapshot.error.toString());
                  }

                  final data = snapshot.data!;
                  return _buildContent(data);
                },
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
        label: const Text('Novo Usuário', style: TextStyle(fontWeight: FontWeight.w500)),
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
              child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
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
                color: SupabaseColors.error.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.error_outline_rounded, size: 40, color: SupabaseColors.error),
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
              style: const TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
            ),
            const SizedBox(height: 20),
            TextButton.icon(
              onPressed: _refreshUsers,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Tentar novamente'),
              style: TextButton.styleFrom(
                backgroundColor: SupabaseColors.brand,
                foregroundColor: SupabaseColors.bg100,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
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
                    .map((user) => _UserCard(
                  user: user,
                  onToggle: () => _toggleUserStatus(user),
                  isLoading: _isLoading,
                  isMe: user.id == Session().myId,
                  canToggle: Session().isSysAdmin && user.id != Session().myId,
                ))
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
          child: _SummaryCard(
            icon: Icons.people_rounded,
            label: 'Total',
            value: summary.total.toString(),
            color: SupabaseColors.brand,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _SummaryCard(
            icon: Icons.check_circle_rounded,
            label: 'Ativos',
            value: summary.active.toString(),
            color: SupabaseColors.success,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _SummaryCard(
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

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, color: color, size: 24),
          ),
          const SizedBox(height: 12),
          Text(
            value,
            style: TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: SupabaseColors.textMuted,
            ),
          ),
        ],
      ),
    );
  }
}

class _UserCard extends StatelessWidget {
  const _UserCard({
    required this.user,
    required this.onToggle,
    required this.isLoading,
    required this.isMe,
    required this.canToggle,
  });

  final UserInfo user;
  final VoidCallback onToggle;
  final bool isLoading;
  final bool isMe;
  final bool canToggle;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: isMe ? SupabaseColors.brand.withOpacity(0.1) : SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isMe ? SupabaseColors.brand.withOpacity(0.3) : SupabaseColors.border,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: user.isActive
                    ? SupabaseColors.success.withOpacity(0.2)
                    : SupabaseColors.error.withOpacity(0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Text(
                  isMe ? 'EU' : user.displayName.substring(0, 1).toUpperCase(),
                  style: TextStyle(
                    color: user.isActive ? SupabaseColors.success : SupabaseColors.error,
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isMe ? '${user.displayName} (você)' : user.displayName,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      decoration: user.isActive ? null : TextDecoration.lineThrough,
                      color: SupabaseColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      const Icon(Icons.account_circle_rounded, size: 12, color: SupabaseColors.textMuted),
                      const SizedBox(width: 4),
                      Text(
                        user.username,
                        style: const TextStyle(fontSize: 12, color: SupabaseColors.textMuted),
                      ),
                      const SizedBox(width: 12),
                      const Icon(Icons.email_rounded, size: 12, color: SupabaseColors.textMuted),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          user.emailHint,
                          style: const TextStyle(fontSize: 12, color: SupabaseColors.textMuted),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: user.isActive
                          ? SupabaseColors.success.withOpacity(0.15)
                          : SupabaseColors.error.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          user.isActive ? Icons.check_circle_rounded : Icons.block_rounded,
                          size: 12,
                          color: user.isActive ? SupabaseColors.success : SupabaseColors.error,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          user.status.toUpperCase(),
                          style: TextStyle(
                            color: user.isActive ? SupabaseColors.success : SupabaseColors.error,
                            fontWeight: FontWeight.w600,
                            fontSize: 10,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            if (isLoading)
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: SupabaseColors.brand.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
                ),
              )
            else if (canToggle)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _IconBtn(
                    icon: Icons.folder_rounded,
                    tooltip: 'Ver projetos',
                    color: SupabaseColors.brand,
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => UserProjectsAdminScreen(
                            userIdHash: user.id,
                            userName: user.username,
                          ),
                        ),
                      );
                    },
                  ),
                  const SizedBox(width: 6),
                  _IconBtn(
                    icon: user.isActive ? Icons.block_rounded : Icons.check_circle_rounded,
                    tooltip: user.isActive ? 'Desativar' : 'Ativar',
                    color: user.isActive ? SupabaseColors.error : SupabaseColors.success,
                    onPressed: onToggle,
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  const _IconBtn({
    required this.icon,
    required this.tooltip,
    required this.color,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Icon(icon, color: color, size: 18),
          ),
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.icon, required this.label, required this.value});
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 14, color: SupabaseColors.textMuted),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: SupabaseColors.textSecondary),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(fontSize: 12, color: SupabaseColors.textMuted),
          ),
        ),
      ],
    );
  }
}

class _ConfirmDialog extends StatelessWidget {
  const _ConfirmDialog({
    required this.title,
    required this.icon,
    required this.iconColor,
    required this.content,
    required this.confirmLabel,
    required this.confirmColor,
  });

  final String title;
  final IconData icon;
  final Color iconColor;
  final Widget content;
  final String confirmLabel;
  final Color confirmColor;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: SupabaseColors.bg200,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: SupabaseColors.border),
      ),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: iconColor.withOpacity(0.15),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(icon, color: iconColor, size: 20),
          ),
          const SizedBox(width: 12),
          Text(title, style: const TextStyle(fontSize: 16, color: SupabaseColors.textPrimary)),
        ],
      ),
      content: content,
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Cancelar', style: TextStyle(color: SupabaseColors.textMuted)),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, true),
          style: TextButton.styleFrom(
            backgroundColor: confirmColor,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          ),
          child: Text(confirmLabel),
        ),
      ],
    );
  }
}

class UserListResponse {
  final List<UserInfo> users;
  final UserSummary summary;
  final int timestamp;

  UserListResponse({required this.users, required this.summary, required this.timestamp});

  factory UserListResponse.fromJson(Map<String, dynamic> json) {
    List<UserInfo> usersList = [];
    if (json['users'] != null) {
      if (json['users'] is List) {
        usersList = (json['users'] as List).map((u) => UserInfo.fromJson(u)).toList();
      }
    }

    return UserListResponse(
      users: usersList,
      summary: UserSummary.fromJson(json['summary'] ?? {}),
      timestamp: json['timestamp'] ?? 0,
    );
  }
}

class UserInfo {
  final String id;
  final String username;
  final String displayName;
  final bool isActive;
  final String status;
  final String emailHint;

  UserInfo({
    required this.id,
    required this.username,
    required this.displayName,
    required this.isActive,
    required this.status,
    required this.emailHint,
  });

  factory UserInfo.fromJson(Map<String, dynamic> json) {
    return UserInfo(
      id: json['id'] ?? '',
      username: json['username'] ?? '',
      displayName: json['display_name'] ?? '',
      isActive: json['is_active'] ?? false,
      status: json['status'] ?? 'unknown',
      emailHint: json['email_hint'] ?? '',
    );
  }
}

class UserSummary {
  final int total;
  final int active;
  final int inactive;

  UserSummary({required this.total, required this.active, required this.inactive});

  factory UserSummary.fromJson(Map<String, dynamic> json) {
    return UserSummary(
      total: json['total'] ?? 0,
      active: json['active'] ?? 0,
      inactive: json['inactive'] ?? 0,
    );
  }
}