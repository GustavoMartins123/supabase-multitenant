import 'package:flutter/material.dart';

import '../supabase_colors.dart';

typedef PasswordStepUpAuthenticator = Future<String> Function(String password);

Future<String?> showStepUpAuthenticationDialog(
  BuildContext context, {
  required String title,
  required String description,
  required PasswordStepUpAuthenticator authenticate,
}) {
  return showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (context) => _StepUpAuthenticationDialog(
      title: title,
      description: description,
      authenticate: authenticate,
    ),
  );
}

class _StepUpAuthenticationDialog extends StatefulWidget {
  const _StepUpAuthenticationDialog({
    required this.title,
    required this.description,
    required this.authenticate,
  });

  final String title;
  final String description;
  final PasswordStepUpAuthenticator authenticate;

  @override
  State<_StepUpAuthenticationDialog> createState() =>
      _StepUpAuthenticationDialogState();
}

class _StepUpAuthenticationDialogState
    extends State<_StepUpAuthenticationDialog> {
  final _password = TextEditingController();
  final _focusNode = FocusNode();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _password.clear();
    _password.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (_password.text.isEmpty) {
      setState(() => _error = 'Digite a senha da sua conta.');
      _focusNode.requestFocus();
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final token = await widget.authenticate(_password.text);
      _password.clear();
      if (mounted) Navigator.pop(context, token);
    } catch (error) {
      _password.clear();
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
      _focusNode.requestFocus();
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_busy,
      child: AlertDialog(
        key: const ValueKey('step-up-authentication-dialog'),
        backgroundColor: SupabaseColors.bg200,
        title: Text(widget.title),
        content: SizedBox(
          width: 430,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.description),
              const SizedBox(height: 8),
              const Text(
                'Use a senha da sua propria conta. Nenhuma senha global do '
                'servidor e necessaria.',
                style: TextStyle(
                  color: SupabaseColors.textMuted,
                  fontSize: 11,
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                key: const ValueKey('step-up-password-field'),
                controller: _password,
                focusNode: _focusNode,
                autofocus: true,
                enabled: !_busy,
                obscureText: _obscure,
                autofillHints: const [AutofillHints.password],
                onSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  labelText: 'Senha atual',
                  errorText: _error,
                  border: const OutlineInputBorder(),
                  prefixIcon: const Icon(Icons.lock_outline),
                  suffixIcon: IconButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => _obscure = !_obscure),
                    icon: Icon(
                      _obscure ? Icons.visibility : Icons.visibility_off,
                    ),
                  ),
                ),
              ),
              if (_busy) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(
                  key: ValueKey('step-up-authentication-progress'),
                  minHeight: 2,
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _busy ? null : () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: _busy ? null : _submit,
            child: Text(_busy ? 'Verificando...' : 'Reautenticar'),
          ),
        ],
      ),
    );
  }
}
