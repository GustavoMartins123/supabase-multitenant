import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:seletor_de_projetos/main.dart';
import 'package:seletor_de_projetos/session.dart';
import 'package:seletor_de_projetos/userProjectsAdminScreen.dart';
import 'createUserDialog.dart';

class AdminUsersPage extends StatefulWidget {
  const AdminUsersPage({super.key});

  @override
  State<AdminUsersPage> createState() => _AdminUsersPageState();
}

class _AdminUsersPageState extends State<AdminUsersPage> with SingleTickerProviderStateMixin {
  late Future<UserListResponse> _usersFuture;
  bool _isLoading = false;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _refreshUsers();

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 500),
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

    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        backgroundColor: isDark ? const Color(0xFF1A1F2E) : Colors.white,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: user.isActive ? Colors.red.withOpacity(0.15) : Colors.green.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                user.isActive ? Icons.block_rounded : Icons.check_circle_rounded,
                color: user.isActive ? Colors.red : Colors.green,
                size: 24,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                user.isActive ? 'Desativar usuário?' : 'Ativar usuário?',
                style: const TextStyle(fontSize: 18),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildInfoRow(Icons.person_rounded, 'Usuário', user.displayName, isDark),
            const SizedBox(height: 8),
            _buildInfoRow(Icons.account_circle_rounded, 'Login', user.username, isDark),
            const SizedBox(height: 8),
            _buildInfoRow(Icons.email_rounded, 'Email', user.emailHint, isDark),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: user.isActive
                    ? Colors.red.withOpacity(0.1)
                    : Colors.green.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: user.isActive
                      ? Colors.red.withOpacity(0.3)
                      : Colors.green.withOpacity(0.3),
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.info_outline_rounded,
                    color: user.isActive ? Colors.red : Colors.green,
                    size: 20,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      user.isActive
                          ? 'Desativar removerá o acesso e pode afetar projetos existentes.'
                          : 'Ativar restaurará o acesso do usuário.',
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.white70 : Colors.black87,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(
              backgroundColor: user.isActive ? Colors.red : Colors.green,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: Text(user.isActive ? 'Desativar' : 'Ativar'),
          ),
        ],
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
        _showSnackBar(
          user.isActive
              ? 'Usuário ${user.username} desativado com sucesso'
              : 'Usuário ${user.username} ativado com sucesso',
          Colors.green,
        );
        _refreshUsers();
      } else {
        final error = jsonDecode(response.body)['error'] ?? 'Erro desconhecido';
        _showSnackBar('Erro: $error', Colors.red);
      }
    } catch (e) {
      _showSnackBar('Erro: $e', Colors.red);
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Widget _buildInfoRow(IconData icon, String label, String value, bool isDark) {
    return Row(
      children: [
        Icon(icon, size: 16, color: isDark ? Colors.white54 : Colors.black54),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: isDark ? Colors.white70 : Colors.black87,
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              fontSize: 13,
              color: isDark ? Colors.white60 : Colors.black54,
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _showCreateUserDialog() async {
    await showDialog(
      context: context,
      builder: (context) => CreateUserDialog(
        onUserCreated: () {
          _refreshUsers();
          _showSnackBar('Usuário criado com sucesso!', Colors.green);
        },
      ),
    );
  }

  void _showSnackBar(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        margin: const EdgeInsets.all(16),
        duration: const Duration(seconds: 4),
      ),
    );
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
              titlePadding: const EdgeInsets.only(left: 60, bottom: 16),
              title: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Gerenciar Usuários',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.white : Colors.black87,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Administração de contas',
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
                child: IconButton(
                  onPressed: _refreshUsers,
                  icon: const Icon(Icons.refresh_rounded),
                  tooltip: 'Atualizar lista',
                  style: IconButton.styleFrom(
                    backgroundColor: isDark
                        ? Colors.white.withOpacity(0.08)
                        : Colors.black.withOpacity(0.05),
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
      floatingActionButton: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [t.colorScheme.primary, t.colorScheme.secondary],
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
          onPressed: _showCreateUserDialog,
          backgroundColor: Colors.transparent,
          elevation: 0,
          icon: const Icon(Icons.person_add_rounded),
          label: const Text('Novo Usuário'),
        ),
      ),
    );
  }

  Widget _buildLoading() {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

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
              'Carregando usuários...',
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

  Widget _buildError(String error) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.all(40),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: Colors.red.withOpacity(0.1),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.error_outline_rounded, size: 64, color: Colors.red),
            ),
            const SizedBox(height: 24),
            Text(
              'Erro ao carregar usuários',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: isDark ? Colors.white : Colors.black87,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              error,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: isDark ? Colors.white60 : Colors.black54,
              ),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: _refreshUsers,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Tentar novamente'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
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
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Column(
            children: [
              _buildSummaryCards(data.summary),
              const SizedBox(height: 24),
              data.users.isEmpty
                  ? _buildEmptyState()
                  : Column(
                children: data.users.map((user) => _UserCard(
                  user: user,
                  onToggle: () => _toggleUserStatus(user),
                  isLoading: _isLoading,
                  isMe: user.id == Session().myId,
                  canToggle: Session().isSysAdmin && user.id != Session().myId,
                )).toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryCards(UserSummary summary) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Row(
      children: [
        Expanded(
          child: _SummaryCard(
            icon: Icons.people_rounded,
            label: 'Total',
            value: summary.total.toString(),
            color: t.colorScheme.primary,
            isDark: isDark,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: _SummaryCard(
            icon: Icons.check_circle_rounded,
            label: 'Ativos',
            value: summary.active.toString(),
            color: Colors.green,
            isDark: isDark,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: _SummaryCard(
            icon: Icons.block_rounded,
            label: 'Inativos',
            value: summary.inactive.toString(),
            color: Colors.red,
            isDark: isDark,
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState() {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.all(40),
      child: Column(
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
              Icons.people_outline_rounded,
              size: 56,
              color: t.colorScheme.primary,
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Nenhum usuário encontrado',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: isDark ? Colors.white : Colors.black87,
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
    required this.isDark,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color color;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isDark
              ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
              : [Colors.white, Colors.grey[50]!],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: color.withOpacity(0.3),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: isDark ? Colors.black.withOpacity(0.3) : Colors.black.withOpacity(0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 32),
          ),
          const SizedBox(height: 16),
          Text(
            value,
            style: TextStyle(
              fontSize: 32,
              fontWeight: FontWeight.bold,
              color: color,
              letterSpacing: -1,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
              color: isDark ? Colors.white54 : Colors.black54,
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
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        gradient: isMe
            ? LinearGradient(
          colors: [
            t.colorScheme.primary.withOpacity(0.15),
            t.colorScheme.secondary.withOpacity(0.1),
          ],
        )
            : LinearGradient(
          colors: isDark
              ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
              : [Colors.white, Colors.grey[50]!],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isMe
              ? t.colorScheme.primary.withOpacity(0.3)
              : (isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08)),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: isDark ? Colors.black.withOpacity(0.3) : Colors.black.withOpacity(0.08),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: user.isActive
                      ? [Colors.green.shade400, Colors.green.shade600]
                      : [Colors.red.shade400, Colors.red.shade600],
                ),
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: (user.isActive ? Colors.green : Colors.red).withOpacity(0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Center(
                child: Text(
                  isMe ? 'EU' : user.displayName.substring(0, 1).toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 20,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isMe ? '${user.displayName} (você)' : user.displayName,
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                      decoration: user.isActive ? null : TextDecoration.lineThrough,
                      color: isDark ? Colors.white : Colors.black87,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(Icons.account_circle_rounded, size: 14, color: isDark ? Colors.white54 : Colors.black54),
                      const SizedBox(width: 6),
                      Text(
                        user.username,
                        style: TextStyle(
                          fontSize: 13,
                          color: isDark ? Colors.white60 : Colors.black54,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(Icons.email_rounded, size: 14, color: isDark ? Colors.white54 : Colors.black54),
                      const SizedBox(width: 6),
                      Text(
                        user.emailHint,
                        style: TextStyle(
                          fontSize: 13,
                          color: isDark ? Colors.white60 : Colors.black54,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: user.isActive
                          ? Colors.green.withOpacity(0.15)
                          : Colors.red.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: user.isActive
                            ? Colors.green.withOpacity(0.3)
                            : Colors.red.withOpacity(0.3),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          user.isActive ? Icons.check_circle_rounded : Icons.block_rounded,
                          size: 14,
                          color: user.isActive ? Colors.green : Colors.red,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          user.status.toUpperCase(),
                          style: TextStyle(
                            color: user.isActive ? Colors.green : Colors.red,
                            fontWeight: FontWeight.bold,
                            fontSize: 11,
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
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: t.colorScheme.primary.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(t.colorScheme.primary),
                  ),
                ),
              )
            else if (canToggle)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.03),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: IconButton(
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
                      icon: Icon(
                        Icons.folder_rounded,
                        color: t.colorScheme.primary,
                      ),
                      tooltip: 'Ver projetos',
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    decoration: BoxDecoration(
                      color: user.isActive
                          ? Colors.red.withOpacity(0.15)
                          : Colors.green.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: IconButton(
                      onPressed: onToggle,
                      icon: Icon(
                        user.isActive ? Icons.block_rounded : Icons.check_circle_rounded,
                        color: user.isActive ? Colors.red : Colors.green,
                      ),
                      tooltip: user.isActive ? 'Desativar usuário' : 'Ativar usuário',
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class UserListResponse {
  final List<UserInfo> users;
  final UserSummary summary;
  final int timestamp;

  UserListResponse({
    required this.users,
    required this.summary,
    required this.timestamp,
  });

  factory UserListResponse.fromJson(Map<String, dynamic> json) {
    List<UserInfo> usersList = [];
    if (json['users'] != null) {
      if (json['users'] is List) {
        usersList = (json['users'] as List)
            .map((u) => UserInfo.fromJson(u))
            .toList();
      } else if (json['users'] is Map && (json['users'] as Map).isEmpty) {
        usersList = [];
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

  UserSummary({
    required this.total,
    required this.active,
    required this.inactive,
  });

  factory UserSummary.fromJson(Map<String, dynamic> json) {
    return UserSummary(
      total: json['total'] ?? 0,
      active: json['active'] ?? 0,
      inactive: json['inactive'] ?? 0,
    );
  }
}
