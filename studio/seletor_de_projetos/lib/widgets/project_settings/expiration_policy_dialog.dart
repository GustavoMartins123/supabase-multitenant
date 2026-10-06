import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../supabase_colors.dart';

class ExpirationPolicySelection {
  const ExpirationPolicySelection(this.days);

  final int? days;
}

String expirationLabel(int? days) =>
    days == null ? 'Não expira' : '$days dias';

class ExpirationPolicyDialog extends StatefulWidget {
  const ExpirationPolicyDialog({super.key, required this.initialDays});

  final int? initialDays;

  @override
  State<ExpirationPolicyDialog> createState() =>
      _ExpirationPolicyDialogState();
}

class _ExpirationPolicyDialogState extends State<ExpirationPolicyDialog> {
  static const _presetDays = {90, 180, 365};
  late String _choice;
  late final TextEditingController _customDays;
  String? _error;

  @override
  void initState() {
    super.initState();
    final initialDays = widget.initialDays;
    if (initialDays == null) {
      _choice = 'never';
    } else if (_presetDays.contains(initialDays)) {
      _choice = initialDays.toString();
    } else {
      _choice = 'custom';
    }
    _customDays = TextEditingController(
      text: initialDays == null || _presetDays.contains(initialDays)
          ? ''
          : initialDays.toString(),
    );
  }

  @override
  void dispose() {
    _customDays.dispose();
    super.dispose();
  }

  void _submit() {
    int? days;
    if (_choice != 'never') {
      days = _choice == 'custom'
          ? int.tryParse(_customDays.text)
          : int.parse(_choice);
      if (days == null || days < 1 || days > 3650) {
        setState(() => _error = 'Informe um intervalo entre 1 e 3650 dias.');
        return;
      }
    }
    Navigator.pop(context, ExpirationPolicySelection(days));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: SupabaseColors.bg200,
      title: const Text('Expiração da chave'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'O lifetime da credencial não altera a janela curta de '
              'revelação única nem o lifetime de JWTs e sessões.',
              style: TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _choice,
              decoration: const InputDecoration(labelText: 'Política'),
              items: const [
                DropdownMenuItem(value: 'never', child: Text('Não expira')),
                DropdownMenuItem(value: '90', child: Text('90 dias')),
                DropdownMenuItem(value: '180', child: Text('180 dias')),
                DropdownMenuItem(value: '365', child: Text('365 dias')),
                DropdownMenuItem(value: 'custom', child: Text('Personalizado')),
              ],
              onChanged: (value) => setState(() {
                _choice = value!;
                _error = null;
              }),
            ),
            if (_choice == 'custom') ...[
              const SizedBox(height: 12),
              TextField(
                controller: _customDays,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(
                  labelText: 'Intervalo em dias',
                  hintText: '1 a 3650',
                ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(
                _error!,
                style: const TextStyle(color: SupabaseColors.error),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        TextButton(onPressed: _submit, child: const Text('Aplicar')),
      ],
    );
  }
}
