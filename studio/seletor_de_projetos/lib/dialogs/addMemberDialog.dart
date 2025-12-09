import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/models/AllUsers.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class AddMemberDialog extends StatefulWidget {
  final Future<void> Function() loadUsers;
  final List<AvailableUserShort> Function() getUsers;
  final Future<void> Function(String userId, String role) onAdd;

  const AddMemberDialog({
    super.key,
    required this.loadUsers,
    required this.getUsers,
    required this.onAdd,
  });

  @override
  State<AddMemberDialog> createState() => _AddMemberDialogState();
}

class _AddMemberDialogState extends State<AddMemberDialog>
    with SingleTickerProviderStateMixin {
  List<AvailableUserShort> _users = [];
  List<AvailableUserShort> _shown = [];
  AvailableUserShort? _sel;
  bool _loading = true;
  String? _error;
  final _searchCtl = TextEditingController();
  late AnimationController _animController;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _fetch();
    _searchCtl.addListener(_filter);

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

  Future<void> _fetch() async {
    try {
      await widget.loadUsers();
      _users = widget.getUsers();
      _shown = _users;
      setState(() => _loading = false);
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _filter() {
    final q = _searchCtl.text.toLowerCase();
    setState(() {
      _shown = q.isEmpty
          ? _users
          : _users.where((u) => u.displayName.toLowerCase().contains(q)).toList();
    });
  }

  @override
  void dispose() {
    _searchCtl.dispose();
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scaleAnimation,
      child: Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          constraints: const BoxConstraints(maxWidth: 480, maxHeight: 600),
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
                        color: SupabaseColors.brand.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.person_add_alt_1_rounded,
                        color: SupabaseColors.brand,
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Adicionar Membro',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: SupabaseColors.textPrimary,
                            ),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Selecione um usuário da lista',
                            style: TextStyle(fontSize: 12, color: SupabaseColors.textMuted),
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
                    _PrimaryButton(
                      label: 'Adicionar',
                      icon: Icons.check_rounded,
                      enabled: _sel != null,
                      onPressed: _sel == null
                          ? null
                          : () async {
                        await widget.onAdd(_sel!.userId, 'member');
                        if (context.mounted) Navigator.pop(context);
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
            child: CircularProgressIndicator(strokeWidth: 2, color: SupabaseColors.brand),
          ),
          SizedBox(height: 16),
          Text(
            'Carregando usuários...',
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
            Text(
              _error!,
              style: const TextStyle(color: SupabaseColors.error, fontSize: 13),
              textAlign: TextAlign.center,
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
        children: [
          TextFormField(
            controller: _searchCtl,
            style: const TextStyle(fontSize: 13, color: SupabaseColors.textPrimary),
            decoration: InputDecoration(
              hintText: 'Buscar usuário…',
              hintStyle: const TextStyle(color: SupabaseColors.textMuted, fontSize: 13),
              prefixIcon: const Icon(Icons.search_rounded, color: SupabaseColors.textMuted, size: 18),
              filled: true,
              fillColor: SupabaseColors.bg300,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(6),
                borderSide: const BorderSide(color: SupabaseColors.border),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(6),
                borderSide: const BorderSide(color: SupabaseColors.border),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(6),
                borderSide: const BorderSide(color: SupabaseColors.brand, width: 2),
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            ),
          ),
          const SizedBox(height: 16),

          Expanded(
            child: _shown.isEmpty ? _buildEmptyState() : _buildUserList(),
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
                  '${_shown.length} ${_shown.length == 1 ? 'usuário disponível' : 'usuários disponíveis'}',
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
              itemCount: _shown.length,
              itemBuilder: (_, i) {
                final u = _shown[i];
                final sel = u == _sel;

                return Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () => setState(() => _sel = u),
                    borderRadius: BorderRadius.circular(6),
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      margin: const EdgeInsets.only(bottom: 2),
                      decoration: BoxDecoration(
                        color: sel ? SupabaseColors.brand.withOpacity(0.1) : null,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: sel ? SupabaseColors.brand.withOpacity(0.3) : Colors.transparent,
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 36,
                            height: 36,
                            decoration: BoxDecoration(
                              color: sel
                                  ? SupabaseColors.brand.withOpacity(0.2)
                                  : SupabaseColors.surface200,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Center(
                              child: Text(
                                u.displayName[0].toUpperCase(),
                                style: TextStyle(
                                  color: sel ? SupabaseColors.brand : SupabaseColors.textSecondary,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 14,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),

                          Expanded(
                            child: Text(
                              u.displayName,
                              style: TextStyle(
                                fontWeight: sel ? FontWeight.w600 : FontWeight.w500,
                                fontSize: 13,
                                color: SupabaseColors.textPrimary,
                              ),
                            ),
                          ),

                          SizedBox(
                            width: 20,
                            height: 20,
                            child: Radio<AvailableUserShort>(
                              value: u,
                              groupValue: _sel,
                              onChanged: (_) => setState(() => _sel = u),
                              activeColor: SupabaseColors.brand,
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
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: SupabaseColors.surface200,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(
              Icons.people_outline_rounded,
              size: 32,
              color: SupabaseColors.textMuted,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Nenhum usuário disponível',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: SupabaseColors.textSecondary,
            ),
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

class _PrimaryButton extends StatefulWidget {
  const _PrimaryButton({
    required this.label,
    required this.icon,
    required this.enabled,
    required this.onPressed,
  });
  final String label;
  final IconData icon;
  final bool enabled;
  final VoidCallback? onPressed;

  @override
  State<_PrimaryButton> createState() => _PrimaryButtonState();
}

class _PrimaryButtonState extends State<_PrimaryButton> {
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
              ? (_hover ? SupabaseColors.brandLight : SupabaseColors.brand)
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
                    color: enabled ? SupabaseColors.bg100 : SupabaseColors.textMuted,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    widget.label,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: enabled ? SupabaseColors.bg100 : SupabaseColors.textMuted,
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