import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/models/AllUsers.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class TransferProjectDialog extends StatefulWidget {
  final String projectName;
  final Function(String) onTransfer;
  final Future<List<AvailableUser>> Function(String projectName) loadAvailableUsers;

  const TransferProjectDialog({
    super.key,
    required this.projectName,
    required this.onTransfer,
    required this.loadAvailableUsers,
  });

  @override
  State<TransferProjectDialog> createState() => TransferProjectDialogState();
}

class TransferProjectDialogState extends State<TransferProjectDialog>
    with SingleTickerProviderStateMixin {
  List<AvailableUser> _availableUsers = [];
  bool _loading = true;
  String? _error;
  AvailableUser? _selectedUser;
  late AnimationController _animController;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _loadUsers();

    _animController = AnimationController(
      duration: const Duration(milliseconds: 250),
      vsync: this,
    );
    _scaleAnimation = CurvedAnimation(
      parent: _animController,
      curve: Curves.easeOut,
    );
    _animController.forward();
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
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
    return ScaleTransition(
      scale: _scaleAnimation,
      child: Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          constraints: const BoxConstraints(maxWidth: 520, maxHeight: 600),
          decoration: BoxDecoration(
            color: SupabaseColors.bg200,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: SupabaseColors.border),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(20),
                decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: SupabaseColors.border)),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: SupabaseColors.warning.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.swap_horiz_rounded,
                        color: SupabaseColors.warning,
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Transferir Projeto',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: SupabaseColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: SupabaseColors.brand.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              widget.projectName,
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                fontFamily: 'monospace',
                                color: SupabaseColors.brand,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    _CloseBtn(onPressed: () => Navigator.pop(context)),
                  ],
                ),
              ),

              Expanded(
                child: _loading
                    ? _buildLoading()
                    : _error != null
                    ? _buildError()
                    : _buildContent(),
              ),

              Container(
                padding: const EdgeInsets.all(16),
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: SupabaseColors.border)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      style: TextButton.styleFrom(
                        foregroundColor: SupabaseColors.textSecondary,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                      ),
                      child: const Text('Cancelar', style: TextStyle(fontSize: 13)),
                    ),
                    const SizedBox(width: 8),
                    _ActionButton(
                      label: 'Transferir',
                      icon: Icons.check_rounded,
                      color: SupabaseColors.warning,
                      enabled: _selectedUser != null,
                      onPressed: _selectedUser == null
                          ? null
                          : () async {
                        final userId = _selectedUser!.userId;
                        try {
                          await widget.onTransfer(userId);
                          if (mounted) Navigator.pop(context);
                        } catch (e) {
                          _showSnack('Erro ao transferir: $e', SupabaseColors.error);
                        }
                      },
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLoading() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 32,
            height: 32,
            child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.warning),
          ),
          SizedBox(height: 16),
          Text(
            'Carregando usuários disponíveis...',
            style: TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
          ),
        ],
      ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: SupabaseColors.error.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.error_outline_rounded, size: 32, color: SupabaseColors.error),
            ),
            const SizedBox(height: 16),
            const Text(
              'Erro ao carregar usuários',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: SupabaseColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _error!,
              style: const TextStyle(color: SupabaseColors.error, fontSize: 12),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            TextButton.icon(
              onPressed: () {
                setState(() {
                  _loading = true;
                  _error = null;
                });
                _loadUsers();
              },
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('Tentar Novamente'),
              style: TextButton.styleFrom(
                backgroundColor: SupabaseColors.error,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: SupabaseColors.warning.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(
                  Icons.person_search_rounded,
                  size: 16,
                  color: SupabaseColors.warning,
                ),
              ),
              const SizedBox(width: 10),
              const Text(
                'Selecione o novo proprietário',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: SupabaseColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          Expanded(
            child: _availableUsers.isEmpty ? _buildEmptyState() : _buildUserList(),
          ),
        ],
      ),
    );
  }

  Widget _buildUserList() {
    return Container(
      decoration: BoxDecoration(
        color: SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: SupabaseColors.border)),
            ),
            child: Row(
              children: [
                const Icon(Icons.people_rounded, size: 14, color: SupabaseColors.textMuted),
                const SizedBox(width: 6),
                Text(
                  '${_availableUsers.length} ${_availableUsers.length == 1 ? 'usuário disponível' : 'usuários disponíveis'}',
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    color: SupabaseColors.textMuted,
                  ),
                ),
              ],
            ),
          ),

          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(4),
              itemCount: _availableUsers.length,
              itemBuilder: (context, index) {
                final user = _availableUsers[index];
                final isSelected = _selectedUser == user;

                return Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () => setState(() => _selectedUser = user),
                    borderRadius: BorderRadius.circular(6),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 2),
                      decoration: BoxDecoration(
                        color: isSelected ? SupabaseColors.warning.withOpacity(0.1) : null,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: isSelected
                              ? SupabaseColors.warning.withOpacity(0.3)
                              : Colors.transparent,
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? SupabaseColors.warning.withOpacity(0.2)
                                  : SupabaseColors.surface200,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Center(
                              child: Text(
                                user.displayName.isNotEmpty
                                    ? user.displayName[0].toUpperCase()
                                    : '?',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  color: isSelected
                                      ? SupabaseColors.warning
                                      : SupabaseColors.textSecondary,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),

                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  user.displayName,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 13,
                                    color: SupabaseColors.textPrimary,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  '@${user.username}',
                                  style: const TextStyle(
                                    fontSize: 11,
                                    color: SupabaseColors.textMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: user.isActive
                                  ? SupabaseColors.success.withOpacity(0.15)
                                  : SupabaseColors.surface300,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              user.isActive ? 'Ativo' : 'Inativo',
                              style: TextStyle(
                                fontSize: 9,
                                fontWeight: FontWeight.w600,
                                color: user.isActive
                                    ? SupabaseColors.success
                                    : SupabaseColors.textMuted,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),

                          SizedBox(
                            width: 20,
                            height: 20,
                            child: Radio<AvailableUser>(
                              value: user,
                              groupValue: _selectedUser,
                              onChanged: (value) => setState(() => _selectedUser = value),
                              activeColor: SupabaseColors.warning,
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
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
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: SupabaseColors.surface200,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(
              Icons.person_off_rounded,
              size: 28,
              color: SupabaseColors.textMuted,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Nenhum usuário disponível',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: SupabaseColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Não há usuários disponíveis\npara receber este projeto.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: SupabaseColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _CloseBtn extends StatelessWidget {
  const _CloseBtn({required this.onPressed});
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(4),
        child: const Padding(
          padding: EdgeInsets.all(4),
          child: Icon(Icons.close_rounded, size: 18, color: SupabaseColors.textMuted),
        ),
      ),
    );
  }
}

class _ActionButton extends StatefulWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.enabled,
    required this.onPressed,
  });
  final String label;
  final IconData icon;
  final Color color;
  final bool enabled;
  final VoidCallback? onPressed;

  @override
  State<_ActionButton> createState() => _ActionButtonState();
}

class _ActionButtonState extends State<_ActionButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final enabled = widget.enabled;

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          color: enabled
              ? (_hover ? widget.color.withOpacity(0.9) : widget.color)
              : SupabaseColors.surface300,
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
                    color: enabled ? Colors.white : SupabaseColors.textMuted,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    widget.label,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: enabled ? Colors.white : SupabaseColors.textMuted,
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