import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/models/AllUsers.dart';
class AddMemberDialog extends StatefulWidget {
  final Future<void> Function() loadUsers;              // dispara fetch da lista
  final List<AvailableUserShort> Function() getUsers;       // devolve lista já carregada
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

class _AddMemberDialogState extends State<AddMemberDialog> {
  List<AvailableUserShort> _users   = [];
  List<AvailableUserShort> _shown   = [];
  AvailableUserShort?       _sel;
  bool                  _loading = true;
  String?               _error;
  final _searchCtl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _fetch();
    _searchCtl.addListener(_filter);
  }

  Future<void> _fetch() async {
    try {
      await widget.loadUsers();                     // carrega via tela pai
      _users = widget.getUsers();                   // lê lista pronta
      _shown = _users;
      setState(() => _loading = false);
    } catch (e) {
      setState(() {
        _error   = e.toString();
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
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          Icon(Icons.person_add_alt_1, color: Colors.blue[700]),
          const SizedBox(width: 8),
          const Text('Adicionar membro'),
        ],
      ),
      content: SizedBox(
        width: 420, height: 480,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
            ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
            : Column(
          children: [
            TextField(
              controller: _searchCtl,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar usuário…',
                isDense: true,
              ),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: _shown.isEmpty
                  ? const Center(child: Text('Nenhum usuário disponível'))
                  : _UserList(
                users: _shown,
                selected: _sel,
                onSelect: (u) => setState(() => _sel = u),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancelar')),
        ElevatedButton.icon(
          icon: const Icon(Icons.check),
          label: const Text('Adicionar'),
          onPressed: _sel == null
              ? null
              : () async {
            await widget.onAdd(_sel!.userId, 'member');
            if (context.mounted) Navigator.pop(context);
          },
        ),
      ],
    );
  }
}

/*──── lista interna reutilizável ─────────────────────────────*/

class _UserList extends StatelessWidget {
  final List<AvailableUserShort> users;
  final AvailableUserShort? selected;
  final ValueChanged<AvailableUserShort> onSelect;
  const _UserList({required this.users, required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(
      border: Border.all(color: Colors.grey[300]!),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          width: double.infinity,
          decoration: BoxDecoration(
            color: Colors.grey[50],
            borderRadius: const BorderRadius.vertical(top: Radius.circular(8)),
          ),
          child: Text(
            '${users.length} usuário(s) disponível(is)',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
          ),
        ),
        Expanded(
          child: ListView.separated(
            itemCount: users.length,
            separatorBuilder: (_, __) => Divider(height: 1, color: Colors.grey[200]),
            itemBuilder: (_, i) {
              final u   = users[i];
              final sel = u == selected;
              return InkWell(
                onTap: () => onSelect(u),
                child: Container(
                  color: sel ? Colors.blue[50] : null,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 18,
                        backgroundColor: sel ? Colors.blue[200] : Colors.grey[200],
                        child: Text(u.displayName[0].toUpperCase(),
                            style: TextStyle(
                              color: sel ? Colors.blue[700] : Colors.grey[800],
                              fontWeight: FontWeight.bold,
                            )),
                      ),
                      const SizedBox(width: 12),
                      Expanded(child: Text(u.displayName)),
                      Radio<AvailableUserShort>(
                        value: u,
                        groupValue: selected,
                        onChanged: (_) => onSelect(u),
                        activeColor: Colors.blue,
                      ),
                    ],
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