import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/opaque_api_key.dart';
import '../../providers/opaque_api_keys_provider.dart';
import '../../supabase_colors.dart';

class ClaimedOpaqueApiKeyDialog extends StatefulWidget {
  const ClaimedOpaqueApiKeyDialog({
    super.key,
    required this.secret,
    required this.reveal,
    required this.initiallyCopied,
    required this.initialClipboardError,
  });

  final String secret;
  final OpaqueApiKeyReveal reveal;
  final bool initiallyCopied;
  final String? initialClipboardError;

  @override
  State<ClaimedOpaqueApiKeyDialog> createState() =>
      _ClaimedOpaqueApiKeyDialogState();
}

class _ClaimedOpaqueApiKeyDialogState
    extends State<ClaimedOpaqueApiKeyDialog> {
  late bool _copied = widget.initiallyCopied;
  late String? _clipboardError = widget.initialClipboardError;

  Future<void> _copy() async {
    try {
      await Clipboard.setData(ClipboardData(text: widget.secret));
      if (!mounted) return;
      setState(() {
        _copied = true;
        _clipboardError = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _clipboardError = opaqueApiKeyErrorMessage(error));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: const ValueKey('claimed-opaque-api-key-dialog'),
      backgroundColor: SupabaseColors.bg200,
      title: const Text('API key do projeto'),
      content: SizedBox(
        width: 560,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Trate o valor como segredo: qualquer pessoa com ele fala com o '
              'projeto até a chave ser rotacionada.',
              style: TextStyle(color: SupabaseColors.warning),
            ),
            const SizedBox(height: 8),
            Text(
              '${widget.reveal.slotName} · ${widget.reveal.kind}',
              style: const TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 12),
            SelectableText(
              widget.secret,
              key: const ValueKey('claimed-opaque-api-key-plaintext'),
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
            ),
            if (_copied) ...[
              const SizedBox(height: 8),
              const Text(
                'Copiada para a área de transferência.',
                style: TextStyle(color: SupabaseColors.success, fontSize: 11),
              ),
            ],
            if (_clipboardError != null) ...[
              const SizedBox(height: 8),
              Text(
                'Não foi possível copiar automaticamente: $_clipboardError',
                style: const TextStyle(
                  color: SupabaseColors.error,
                  fontSize: 11,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _copy,
          child: Text(_copied ? 'Copiar novamente' : 'Copiar'),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, _copied),
          child: const Text('Fechar'),
        ),
      ],
    );
  }
}
