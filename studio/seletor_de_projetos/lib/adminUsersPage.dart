// admin_users_page.dart
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

class _AdminUsersPageState extends State<AdminUsersPage> {
  late Future<UserListResponse> _usersFuture;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _refreshUsers();
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
      builder: (ctx) => AlertDialog(
        title: Text(user.isActive ? 'Desativar usuário?' : 'Ativar usuário?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Usuário: ${user.displayName}'),
            Text('Login: ${user.username}'),
            Text('Email: ${user.emailHint}'),
            const SizedBox(height: 16),
            Text(
              user.isActive
                  ? 'Desativar removerá o acesso e pode afetar projetos existentes.'
                  : 'Ativar restaurará o acesso do usuário.',
              style: Theme.of(ctx).textTheme.bodySmall,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: user.isActive ? Colors.red : Colors.green,
              foregroundColor: Colors.white,
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
        duration: const Duration(seconds: 4),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gerenciar Usuários'),
        backgroundColor: Theme.of(context).colorScheme.surfaceVariant,
        actions: [
          IconButton(
            onPressed: _refreshUsers,
            icon: const Icon(Icons.refresh),
            tooltip: 'Atualizar lista',
          ),
        ],
      ),
      body: FutureBuilder<UserListResponse>(
        future: _usersFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.error, size: 64, color: Colors.red),
                  const SizedBox(height: 16),
                  Text(
                    'Erro ao carregar usuários',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    snapshot.error.toString(),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _refreshUsers,
                    child: const Text('Tentar novamente'),
                  ),
                ],
              ),
            );
          }

          final data = snapshot.data!;

          return Column(
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                margin: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _SummaryItem(
                      icon: Icons.people,
                      label: 'Total',
                      value: data.summary.total.toString(),
                      color: Colors.blue,
                    ),
                    _SummaryItem(
                      icon: Icons.check_circle,
                      label: 'Ativos',
                      value: data.summary.active.toString(),
                      color: Colors.green,
                    ),
                    _SummaryItem(
                      icon: Icons.block,
                      label: 'Inativos',
                      value: data.summary.inactive.toString(),
                      color: Colors.red,
                    ),
                  ],
                ),
              ),

              Expanded(
                child: data.users.isEmpty
                    ? const Center(
                  child: Text('Nenhum usuário encontrado'),
                )
                    : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: data.users.length,
                  itemBuilder: (context, index) {
                    final user = data.users[index];
                    return _UserCard(
                      user: user,
                      onToggle: () => _toggleUserStatus(user),
                      isLoading: _isLoading,
                      isMe: user.id == Session().myId,
                      canToggle: Session().isSysAdmin && user.id != Session().myId,
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showCreateUserDialog,
        icon: const Icon(Icons.person_add),
        label: const Text('Novo Usuário'),
        tooltip: 'Adicionar novo usuário',
      ),
    );
  }
}

class _SummaryItem extends StatelessWidget {
  const _SummaryItem({
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
    return Column(
      children: [
        Icon(icon, color: color, size: 32),
        const SizedBox(height: 4),
        Text(
          value,
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
        Text(
          label,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
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
    return Card(
      color: isMe ? Colors.green.shade50 : null,
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: user.isActive ? Colors.green : Colors.red,
          child: Text(
            isMe ? 'EU' : user.displayName.substring(0, 1).toUpperCase(),
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        title: Text(
          isMe ? '${user.displayName} (você)' : user.displayName,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            decoration: user.isActive ? null : TextDecoration.lineThrough,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Login: ${user.username}'),
            Text('Email: ${user.emailHint}'),
            Row(
              children: [
                Icon(
                  user.isActive ? Icons.check_circle : Icons.block,
                  size: 16,
                  color: user.isActive ? Colors.green : Colors.red,
                ),
                const SizedBox(width: 4),
                Text(
                  user.status.toUpperCase(),
                  style: TextStyle(
                    color: user.isActive ? Colors.green : Colors.red,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ],
        ),
        trailing: isLoading
            ? const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ) :
            canToggle?
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
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
              icon: Icon(Icons.manage_accounts),
            ),
            IconButton(
              onPressed: onToggle,
              icon: Icon(
                user.isActive ? Icons.block : Icons.check_circle,
                color: user.isActive ? Colors.red : Colors.green,
              ),
              tooltip: user.isActive ? 'Desativar usuário' : 'Ativar usuário',
            ),
          ],
        ) : null,
        isThreeLine: true,
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