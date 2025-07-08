import 'package:flutter/material.dart';

import '../models/AllUsers.dart';

class TransferProjectDialog extends StatefulWidget {
  final String projectName;
  final Function(String) onTransfer;
  final Future<List<AvailableUser>> Function(String projectName) loadAvailableUsers;
  const TransferProjectDialog({
    Key? key,
    required this.projectName,
    required this.onTransfer,
    required this.loadAvailableUsers
  }) : super(key: key);

  @override
  State<TransferProjectDialog> createState() => TransferProjectDialogState();
}

class TransferProjectDialogState extends State<TransferProjectDialog> {
  List<AvailableUser> _availableUsers = [];
  bool _loading = true;
  String? _error;
  AvailableUser? _selectedUser;

  @override
  void initState() {
    super.initState();
    _loadUsers();
  }

  Future<void> _loadUsers() async {
    try {
      final users = await widget.loadAvailableUsers(widget.projectName);
      setState(() {
        _availableUsers = users;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          Icon(Icons.swap_horiz, color: Colors.blue[700]),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Transferir "${widget.projectName}"',
              style: const TextStyle(fontSize: 18),
            ),
          ),
        ],
      ),
      content: SizedBox(
        width: double.maxFinite,
        height: 400,
        child: _loading
            ? const Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('Carregando usuários disponíveis...'),
            ],
          ),
        )
            : _error != null
            ? Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.error_outline, size: 48, color: Colors.red[400]),
              const SizedBox(height: 16),
              Text(
                'Erro ao carregar usuários',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: Colors.red[700],
                ),
              ),
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  _error!,
                  style: TextStyle(color: Colors.red[600]),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: () {
                  setState(() {
                    _loading = true;
                    _error = null;
                  });
                  _loadUsers();
                },
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar Novamente'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue,
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
        )
            : Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            Row(
              children: [
                Icon(Icons.person_search, size: 20, color: Colors.grey[700]),
                const SizedBox(width: 8),
                const Text(
                  'Selecione o novo proprietário:',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Lista de usuários
            Expanded(
              child: _availableUsers.isEmpty
                  ? Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.person_off, size: 64, color: Colors.grey[400]),
                    const SizedBox(height: 16),
                    const Text(
                      'Nenhum usuário disponível',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                        color: Colors.grey,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Não há usuários disponíveis para receber este projeto.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey[600],
                      ),
                    ),
                  ],
                ),
              )
                  : Container(
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey[300]!),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  children: [
                    // Header da lista
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.grey[50],
                        borderRadius: const BorderRadius.only(
                          topLeft: Radius.circular(8),
                          topRight: Radius.circular(8),
                        ),
                      ),
                      child: Row(
                        children: [
                          Text(
                            '${_availableUsers.length} usuário(s) disponível(is)',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: Colors.grey[700],
                            ),
                          ),
                        ],
                      ),
                    ),
                    // Lista de usuários
                    Expanded(
                      child: ListView.builder(
                        itemCount: _availableUsers.length,
                        itemBuilder: (context, index) {
                          final user = _availableUsers[index];
                          final isSelected = _selectedUser == user;

                          return Container(
                            decoration: BoxDecoration(
                              color: isSelected ? Colors.blue[50] : null,
                              border: index > 0
                                  ? Border(top: BorderSide(color: Colors.grey[200]!))
                                  : null,
                            ),
                            child: InkWell(
                              onTap: () {
                                setState(() {
                                  _selectedUser = user;
                                });
                              },
                              child: Padding(
                                padding: const EdgeInsets.all(16),
                                child: Row(
                                  children: [
                                    // Avatar
                                    CircleAvatar(
                                      radius: 20,
                                      backgroundColor: isSelected
                                          ? Colors.blue[200]
                                          : Colors.grey[200],
                                      child: Text(
                                        user.displayName.isNotEmpty
                                            ? user.displayName[0].toUpperCase()
                                            : '?',
                                        style: TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.bold,
                                          color: isSelected
                                              ? Colors.blue[700]
                                              : Colors.grey[700],
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 12),

                                    // Informações do usuário
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            user.displayName,
                                            style: TextStyle(
                                              fontWeight: FontWeight.w500,
                                              fontSize: 14,
                                              color: isSelected
                                                  ? Colors.blue[800]
                                                  : Colors.black87,
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            '@${user.username}',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: isSelected
                                                  ? Colors.blue[600]
                                                  : Colors.grey[600],
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),

                                    // Status e radio button
                                    Column(
                                      crossAxisAlignment: CrossAxisAlignment.end,
                                      children: [
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 8, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: user.isActive
                                                ? Colors.green[100]
                                                : Colors.grey[100],
                                            borderRadius: BorderRadius.circular(12),
                                          ),
                                          child: Text(
                                            user.isActive ? 'Ativo' : 'Inativo',
                                            style: TextStyle(
                                              fontSize: 10,
                                              fontWeight: FontWeight.w500,
                                              color: user.isActive
                                                  ? Colors.green[700]
                                                  : Colors.grey[700],
                                            ),
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Radio<AvailableUser>(
                                          value: user,
                                          groupValue: _selectedUser,
                                          onChanged: (value) {
                                            setState(() {
                                              _selectedUser = value;
                                            });
                                          },
                                          activeColor: Colors.blue,
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        ElevatedButton.icon(
          onPressed: _selectedUser == null
              ? null
              : () async {
            final userId = _selectedUser!.userId;
            try {
              await widget.onTransfer(userId);
              if (mounted) Navigator.pop(context);
            } catch (e) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Erro ao transferir: $e')),
              );
            }
          },
          icon: const Icon(Icons.check),
          label: const Text('Transferir'),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.blue,
            foregroundColor: Colors.white,
          ),
        ),
      ],
    );
  }
}