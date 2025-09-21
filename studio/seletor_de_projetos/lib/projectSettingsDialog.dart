import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:seletor_de_projetos/services/projectService.dart';
import 'package:seletor_de_projetos/session.dart';
import 'package:jwt_decoder/jwt_decoder.dart';
import 'dialogs/addMemberDialog.dart';
import 'dialogs/transferProjectDialog.dart';
import 'models/AllUsers.dart';
import 'models/projectDockerStatus.dart';

class ProjectSettingsDialog extends StatefulWidget {
  const ProjectSettingsDialog({
    super.key,
    required this.ref,
    required this.anonKey,
  });

  final String ref;
  final String anonKey;
  @override
  State<ProjectSettingsDialog> createState() => _ProjectSettingsDialogState();
}

class _ProjectSettingsDialogState extends State<ProjectSettingsDialog> {
  List<ProjectMember> _currentMembers = [];
  List<AvailableUserShort> _availableUsers = [];
  bool _loadingMembers = true;
  bool _loadingAvailable = false;
  bool _addingMember = false;
  String? _error;
  late String _myProjectRole;
  Future<ProjectDockerStatus>? _statusFuture;
  bool _statusLoading = true;
  String? _statusError;
  late bool _busy;
  @override
  void initState() {
    super.initState();
    _busy = Session().isBusy(widget.ref);
    Session().busyListenable.addListener(_onBusyChanged);
    _loadCurrentMembers();
    _loadStatus();
  }

  void _onBusyChanged() {
    if (!mounted) return;
    final b = Session().isBusy(widget.ref);
    if (b != _busy) {
      setState(() => _busy = b);
      if (!b) {
        _loadStatus();
      }
    }
  }

  @override
  void dispose() {
    Session().busyListenable.removeListener(_onBusyChanged);
    super.dispose();
  }

  void _safeSetState(VoidCallback fn) {
    if (mounted) {
      setState(fn);
    }
  }
  Future<void> _loadCurrentMembers() async {
    _safeSetState(() {
      _loadingMembers = true;
      _error = null;
    });

    try {
      final response = await http.get(
        Uri.parse('/api/projects/${widget.ref}/members'),
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        _safeSetState(() {
          _currentMembers = data
              .map((item) => ProjectMember.fromJson(item))
              .toList();
          final session = Session();
          final me = _currentMembers.firstWhere(
                  (m) => m.user_id == session.myId,
              orElse: () => ProjectMember(user_id: '', role: 'member'));

          _myProjectRole = me.role;
          _loadingMembers = false;
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      setState(() {
        _error = 'Erro ao carregar membros: $e';
        _loadingMembers = false;
      });
    }
  }

  Future<void> _loadAvailableUsersForProject() async {
    _safeSetState(() {
      _loadingAvailable = true;
      _error = null;
    });

    try {
      final response = await http.get(
        Uri.parse('/api/projects/${widget.ref}/available-users'),
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        _safeSetState(() {
          _availableUsers = data
              .map((item) => AvailableUserShort.fromJson(item))
              .toList();
          _loadingAvailable = false;
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _safeSetState(() {
        _error = 'Erro ao carregar usuários disponíveis: $e';
        _loadingAvailable = false;
      });
    }
  }

  Future<void> _addMember(String userId, String role) async {
    _safeSetState(() => _addingMember = true);

    try {
      final response = await http.post(
        Uri.parse('/api/projects/${widget.ref}/members'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'user_id': userId,
          'role': role,
        }),
      );

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Membro adicionado com sucesso!')),
        );
        // Recarrega a lista de membros
        await _loadCurrentMembers();
        _safeSetState(() {
          _availableUsers.removeWhere((user) => user.userId == userId);
        });
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erro ao adicionar membro: $e')),
      );
    } finally {
      _safeSetState(() => _addingMember = false);
    }
  }

  Future<void> _removeMember(String userId) async {
    try {
      final response = await http.delete(
        Uri.parse('/api/projects/${widget.ref}/members/$userId'),
      );;

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Membro removido com sucesso!')),
        );
        await _loadCurrentMembers();
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erro ao remover membro: $e')),
      );
    }
  }

  void _openAddMemberDialog() {
    showDialog(
      context: context,
      barrierDismissible: !_addingMember,
      builder: (_) => AddMemberDialog(
        loadUsers: _loadAvailableUsersForProject,
        getUsers: () => _availableUsers,
        onAdd: _addMember,
      ),
    ).then((_) => _loadCurrentMembers());
  }

  Future<void> _loadStatus() async {
    _safeSetState(() {
      _statusLoading = true;
      _statusError = null;
    });

    try {
      final resp = await http.get(
        Uri.parse('/api/projects/${widget.ref}/status'),
      );

      if (resp.statusCode == 200) {
        final data = ProjectDockerStatus.fromJson(jsonDecode(resp.body));
        _safeSetState(() {
          _statusFuture = Future.value(data);
          _statusLoading = false;
        });
      } else {
        throw Exception('Erro ${resp.statusCode}: ${resp.body}');
      }
    } catch (e) {
      _safeSetState(() {
        _statusError = 'Erro ao obter status: $e';
        _statusLoading = false;
      });
    }
  }

  Widget _buildStatusCard() {
    if (_statusLoading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }

    if (_statusError != null) {
      return Card(
        color: Colors.red.shade50,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(_statusError!, style: const TextStyle(color: Colors.red)),
        ),
      );
    }

    if (_statusFuture == null) {
      return const SizedBox.shrink();
    }

    return FutureBuilder<ProjectDockerStatus>(
      future: _statusFuture,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done || !snap.hasData || snap.hasError) {
          return const Center(child: CircularProgressIndicator());
        }

        final st = snap.data!;
        final isRunning = st.status == 'running';

        final busy = Session().isBusy(widget.ref);

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(
                  isRunning ? Icons.check_circle : Icons.warning,
                  color: isRunning ? Colors.green : Colors.orange,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Containers: ${st.running}/${st.total} – ${st.status.toUpperCase()}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                if (_myProjectRole == 'admin')
                  Row(
                    children: [
                      IconButton(
                        tooltip: 'Start',
                        icon: const Icon(Icons.play_arrow),
                        onPressed: busy ? null : () => _doAction('start'),
                      ),
                      IconButton(
                        tooltip: 'Stop',
                        icon: const Icon(Icons.stop),
                        onPressed: busy ? null : () => _doAction('stop'),
                      ),
                      IconButton(
                        tooltip: 'Restart',
                        icon: const Icon(Icons.restart_alt),
                        onPressed: busy ? null : () => _doAction('restart'),
                      ),
                      if (busy)
                        const Padding(
                          padding: EdgeInsets.only(left: 8),
                          child: SizedBox(
                            width: 20, height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        ),
                    ],
                  ),
              ],
            ),
          ),
        );
      },
    );
  }


  Future<void> _doAction(String action) async {
    final tracker = Session();
    if (tracker.isBusy(widget.ref)) return;

    tracker.setBusy(widget.ref, true);
    try {
      final resp = await http.post(
        Uri.parse('/api/projects/${widget.ref}/$action'),
      );
      if (!mounted) return; // <-- proteção extra!

      if (resp.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Ação $action executada'),
          backgroundColor: Colors.green,
        ));
        await _loadStatus();
      } else {
        final err = jsonDecode(resp.body)['detail'] ?? resp.body;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Falha: $err'),
          backgroundColor: Colors.red,
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Erro: $e'),
          backgroundColor: Colors.red,
        ));
      }
    } finally {
      tracker.setBusy(widget.ref, false);
    }
  }

  Future<void> _deleteProject() async {
    bool sucesso = await ProjectService.confirmAndDeleteProject(context, widget.ref);

    if (sucesso) {
      Navigator.of(context).pop(widget.ref);
    }
  }



  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = Session();
    return AlertDialog(
      title: Text('Configurações: ${widget.ref}'),
      content: SizedBox(
        width: double.maxFinite,
        height: 500,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildStatusCard(),
            const SizedBox(height: 16),
            // Seção da Anon Key
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Título
                    Text(
                      'Anon Key',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),

                    const SizedBox(height: 8),

                    // Linha com chave e botão copiar
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: SelectableText(
                            widget.anonKey.isEmpty ? 'Não disponível' : widget.anonKey,
                            style: theme.textTheme.bodySmall?.copyWith(
                              fontFamily: 'monospace',
                            ),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Copiar anon key',
                          icon: const Icon(Icons.copy_all, size: 18),
                          onPressed: widget.anonKey.isEmpty
                              ? null
                              : () {
                            Clipboard.setData(
                                ClipboardData(text: widget.anonKey));
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Chave copiada')),
                            );
                          },
                        ),
                      ],
                    ),

                    const SizedBox(height: 4),

                    if (widget.anonKey.isNotEmpty)
                      Text(
                        'Expira em: ${DateFormat('dd/MM/yyyy HH:mm').format(JwtDecoder.getExpirationDate(widget.anonKey))}',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: Colors.grey),
                      ),

                    const SizedBox(height: 8),
                    ///Todo - Atenção///
                    // Botão placeholder para gerar nova chave no futuro
                    _myProjectRole == 'admin' ?Align(
                      alignment: Alignment.centerRight,
                      child: ElevatedButton.icon(
                        icon: const Icon(Icons.refresh),
                        label: const Text('Gerar nova chave'),
                        onPressed: null,
                      ),
                    ) : SizedBox.shrink(),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Seção de Membros
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Membros do Projeto',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                 _myProjectRole != 'admin'? SizedBox() : ElevatedButton.icon(
                  onPressed:  _loadingMembers ? null : _openAddMemberDialog,
                  icon: const Icon(Icons.person_add),
                  label: const Text('Adicionar'),
                ) ,
              ],
            ),

            const SizedBox(height: 8),

            // Lista de membros
            Expanded(
              child: _buildMembersList(),
            ),
          ],
        ),
      ),
      actions: [
        if (session.isSysAdmin)
          TextButton(
            onPressed: () => _deleteProject(),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('🗑️ Excluir Projeto'),
          ),
        if (session.isSysAdmin)
            TextButton(
            style: TextButton.styleFrom(foregroundColor: Colors.blue),
            onPressed: () => _showTransferDialog(widget.ref),
            child: const Text('🔁 Transferir Projeto'),
          ),
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Fechar'),
        ),
      ],
    );
  }
  //Para transferir
  Future<List<AvailableUser>> _loadAvailableUsers(String projectName) async {
    try {
      final response = await http.get(
        Uri.parse('/api/admin/projects/$projectName/all-users'),
      );

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(response.body);
        final dynamic usersData = data['users'];
        if (usersData == null || usersData is! List) {
          return <AvailableUser>[];
        }
        final List<dynamic> usersJson = usersData;
        return usersJson
            .map((item) => AvailableUser.fromJson(item))
            .where((user) => user.userId != widget.ref)
            .toList();
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      throw Exception('Erro ao carregar usuários disponíveis: $e');
    }
  }


  Future<void> _transferProject(String projectName, String newOwnerId) async {
    try {
      final response = await http.post(
        Uri.parse('/api/admin/projects/$projectName/transfer'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'new_owner_id': newOwnerId,
        }),
      );

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Projeto "$projectName" transferido com sucesso!')),
        );
      } else {
        throw Exception('Erro ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Erro ao transferir projeto: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  void _showTransferDialog(String projectName) {
    showDialog(
      context: context,
      builder: (context) => TransferProjectDialog(
        projectName: projectName,
        onTransfer: (newOwnerId) => _transferProject(projectName, newOwnerId),
        loadAvailableUsers: _loadAvailableUsers
      ),
    );
  }
  Widget _buildMembersList() {
    if (_loadingMembers) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              _error!,
              style: const TextStyle(color: Colors.red),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadCurrentMembers,
              child: const Text('Tentar Novamente'),
            ),
          ],
        ),
      );
    }

    if (_currentMembers.isEmpty) {
      return const Center(
        child: Text('Nenhum membro encontrado'),
      );
    }

    return ListView.builder(
      itemCount: _currentMembers.length,
      itemBuilder: (context, index) {
        final member = _currentMembers[index];
        final session = Session();
        final isMe      = member.user_id == session.myId;
        final canRemove =
            _myProjectRole == 'admin' &&
                member.role != 'admin' &&
                !isMe;
        return Card(
          color: isMe ? Colors.green.shade50 : null,
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: member.role == 'admin'
                  ? Colors.orange
                  : Colors.blue,
              child: Icon(
                member.role == 'admin'
                    ? Icons.admin_panel_settings
                    : Icons.person,
                color: Colors.white,
              ),
            ),
            title: Text(isMe ? '${member.displayName!} (você)' : member.displayName!,
              style: isMe
                  ? const TextStyle(fontWeight: FontWeight.bold)
                  : null,),
            subtitle: Text('Função: ${member.role}'),
            trailing: canRemove
                ? IconButton(
              icon: const Icon(Icons.remove_circle, color: Colors.red),
              onPressed: () => _showRemoveConfirmation(member),
              tooltip: 'Remover membro',
            )
                : null,
          ),
        );
      },
    );
  }

  void _showRemoveConfirmation(ProjectMember member) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Confirmar Remoção'),
        content: Text(
          'Tem certeza que deseja remover ${member.displayName ?? 'este usuário'} do projeto?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _removeMember(member.user_id);
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Remover'),
          ),
        ],
      ),
    );
  }
}

// Modelos de dados
class ProjectMember {
  final String user_id;
  final String role;
  final String? displayName;

  ProjectMember({
    required this.user_id,
    required this.role,
    this.displayName,
  });

  factory ProjectMember.fromJson(Map<String, dynamic> json) {
    return ProjectMember(
      user_id: json['user_id'] as String,
      displayName: json['display_name'] as String?,
      role: json['role'] as String,
    );
  }
}