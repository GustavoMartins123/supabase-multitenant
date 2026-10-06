import 'package:flutter/material.dart';

import '../../supabase_colors.dart';
import '../secondary_button.dart';
import 'expiration_policy_dialog.dart';

final class CreateOpaqueSlotDraft {
  const CreateOpaqueSlotDraft({
    required this.name,
    required this.kind,
    required this.allowedServices,
    required this.automaticRotationEnabled,
    required this.rotationIntervalDays,
  });

  final String name;
  final String kind;
  final List<String> allowedServices;
  final bool automaticRotationEnabled;
  final int? rotationIntervalDays;
}

class CreateOpaqueSlotDialog extends StatefulWidget {
  const CreateOpaqueSlotDialog({super.key});

  @override
  State<CreateOpaqueSlotDialog> createState() =>
      _CreateOpaqueSlotDialogState();
}

class _CreateOpaqueSlotDialogState extends State<CreateOpaqueSlotDialog> {
  static const _services = [
    'auth',
    'rest',
    'graphql',
    'realtime',
    'storage',
    'functions',
  ];
  static const _captionStyle = TextStyle(
    color: SupabaseColors.textMuted,
    fontSize: 10,
    fontWeight: FontWeight.w600,
  );
  final _name = TextEditingController();
  final _selectedServices = <String>{..._services};
  String _kind = 'publishable';
  bool _automatic = true;
  int? _interval = 90;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _chooseExpirationPolicy() async {
    final selection = await showDialog<ExpirationPolicySelection>(
      context: context,
      builder: (context) => ExpirationPolicyDialog(initialDays: _interval),
    );
    if (selection == null || !mounted) return;
    setState(() {
      _interval = selection.days;
      if (_interval == null) _automatic = false;
    });
  }

  void _submit() {
    final name = _name.text;
    if (!RegExp(r'^[a-z][a-z0-9_-]{2,39}$').hasMatch(name)) {
      setState(() => _error = 'Use 3-40 caracteres: a-z, 0-9, _ ou -.');
      return;
    }
    if (_selectedServices.isEmpty) {
      setState(() => _error = 'Selecione ao menos um servico.');
      return;
    }
    Navigator.pop(
      context,
      CreateOpaqueSlotDraft(
        name: name,
        kind: _kind,
        allowedServices: _selectedServices.toList()..sort(),
        automaticRotationEnabled: _automatic,
        rotationIntervalDays: _interval,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: SupabaseColors.bg200,
      title: const Text('Novo slot de API key'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _name,
                decoration:
                    const InputDecoration(labelText: 'Nome do consumidor'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(labelText: 'Tipo'),
                items: const [
                  DropdownMenuItem(
                      value: 'publishable', child: Text('Publishable')),
                  DropdownMenuItem(value: 'secret', child: Text('Secret')),
                ],
                onChanged: (value) => setState(() => _kind = value!),
              ),
              const SizedBox(height: 12),
              const Text('Servicos permitidos',
                  style: _captionStyle),
              Wrap(
                spacing: 6,
                children: _services
                    .map(
                      (service) => FilterChip(
                        label: Text(service),
                        selected: _selectedServices.contains(service),
                        onSelected: (selected) => setState(() {
                          if (selected) {
                            _selectedServices.add(service);
                          } else {
                            _selectedServices.remove(service);
                          }
                        }),
                      ),
                    )
                    .toList(),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                value: _automatic,
                onChanged: _interval == null
                    ? null
                    : (value) => setState(() => _automatic = value),
                title: const Text('Rotacao automatica'),
                subtitle: _interval == null
                    ? const Text(
                        'Indisponível para chaves sem expiração temporal.',
                      )
                    : null,
              ),
              SecondaryButton(
                label: 'Expiração da chave: ${expirationLabel(_interval)}',
                icon: Icons.timer_outlined,
                onPressed: _chooseExpirationPolicy,
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!,
                    style: const TextStyle(color: SupabaseColors.error)),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        TextButton(
          onPressed: _submit,
          child: const Text('Criar e revelar'),
        ),
      ],
    );
  }
}
