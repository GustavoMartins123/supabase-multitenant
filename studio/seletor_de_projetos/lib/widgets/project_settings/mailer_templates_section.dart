import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/project_repository.dart';
import '../../supabase_colors.dart';
import 'mailer_preview_stub.dart'
    if (dart.library.html) 'mailer_preview_web.dart';
import 'mailer_file_picker_stub.dart'
    if (dart.library.html) 'mailer_file_picker_web.dart';

const _labels = {
  'confirmation': 'Confirmação de cadastro',
  'invite': 'Convite',
  'magic_link': 'Código e link de acesso',
  'recovery': 'Recuperação de senha',
  'email_change': 'Alteração de e-mail',
  'reauthentication': 'Reautenticação',
};

const _historyLabels = {
  'draft': 'Rascunho salvo',
  'draft_default': 'Padrão preparado',
  'publish': 'Publicado',
  'publish_default': 'Padrão publicado',
  'quarantine': 'Preservado para revisão',
  'copy': 'Copiado como rascunho',
  'import': 'Importado como rascunho',
  'import_active': 'Legado migrado como ativo',
  'import_default': 'Padrão da plataforma migrado',
  'save': 'Personalização anterior',
  'reset': 'Padrão restaurado',
};

class MailerTemplatesSection extends ConsumerStatefulWidget {
  const MailerTemplatesSection({super.key, required this.projectRef});
  final String projectRef;

  @override
  ConsumerState<MailerTemplatesSection> createState() =>
      _MailerTemplatesState();
}

class _MailerTemplatesState extends ConsumerState<MailerTemplatesSection> {
  final _editor = TextEditingController();
  List<Map<String, dynamic>> _templates = [];
  String _kind = 'magic_link';
  String? _error;
  String? _message;
  String? _preview;
  List<String> _allowedOrigins = [];
  bool _busy = true;
  bool _dirty = false;

  Map<String, dynamic> get _current =>
      _templates.firstWhere((row) => row['kind'] == _kind);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _editor.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await ref
          .read(projectRepositoryProvider)
          .mailerTemplatesRequest(widget.projectRef);
      if (!mounted) return;
      _allowedOrigins =
          List<String>.from(data['allowed_origins'] as List? ?? []);
      _templates = (data['templates'] as List)
          .map((row) => Map<String, dynamic>.from(row as Map))
          .toList();
      _select(_kind);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _select(String kind) {
    setState(() {
      _kind = kind;
      _editor.text = _current['body'] as String;
      _dirty = false;
      _preview = null;
      _error = null;
      _message = null;
    });
  }

  Future<bool> _confirm(String title, String message) async =>
      await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
                title: Text(title),
                content: Text(message),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Cancelar')),
                  TextButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Continuar')),
                ],
              )) ==
      true;

  Future<void> _changeKind(String kind) async {
    if (_dirty &&
        !await _confirm(
            'Descartar alterações?', 'O HTML editado ainda não foi salvo.')) {
      return;
    }
    if (mounted) _select(kind);
  }

  Future<void> _act(String action) async {
    if (action == 'reset' &&
        !await _confirm('Restaurar padrão?',
            'Será criado um rascunho com o padrão da plataforma. Confirme a publicação para alterar os envios.')) {
      return;
    }
    if (!mounted) return;
    if (action != 'reset' && utf8.encode(_editor.text).length > 1024 * 1024) {
      setState(() => _error = 'O HTML deve ter no máximo 1 MB.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _message = null;
    });
    try {
      final repository = ref.read(projectRepositoryProvider);
      final data = await repository.mailerTemplatesRequest(widget.projectRef,
          kind: _kind,
          operation: action == 'preview' ? 'preview' : null,
          method: action == 'preview'
              ? 'POST'
              : action == 'reset'
                  ? 'DELETE'
                  : 'PUT',
          body: action == 'reset'
              ? {'version': _current['version']}
              : {
                  'body': _editor.text,
                  'version': _current['version'],
                });
      if (!mounted) return;
      setState(() {
        if (action == 'preview') {
          _preview = data['html'] as String;
        } else {
          final index = _templates.indexWhere((row) => row['kind'] == _kind);
          _templates[index] = data;
          _editor.text = data['body'] as String;
          _dirty = false;
          _preview = null;
          _message =
              'Rascunho salvo. Os envios continuam usando a versão publicada.';
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _publish() async {
    final current = Map<String, dynamic>.from(_current);
    final kind = _kind;
    final password = TextEditingController();
    String? token;
    try {
      token = await showDialog<String>(
          context: context,
          barrierDismissible: false,
          builder: (dialogContext) =>
              StatefulBuilder(builder: (context, update) {
                bool sending = _confirming;
                return AlertDialog(
                  title: const Text('Publicar template de e-mail'),
                  content: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(
                        'Confirme sua senha para publicar o rascunho de ${_labels[kind]}. Os próximos envios usarão esta versão.'),
                    const SizedBox(height: 12),
                    TextField(
                        controller: password,
                        obscureText: true,
                        enabled: !sending,
                        autocorrect: false,
                        enableSuggestions: false,
                        decoration: const InputDecoration(
                            labelText: 'Sua senha atual')),
                    if (_confirmationError != null) Text(_confirmationError!),
                  ]),
                  actions: [
                    TextButton(
                        onPressed:
                            sending ? null : () => Navigator.pop(dialogContext),
                        child: const Text('Cancelar')),
                    FilledButton(
                        onPressed: sending
                            ? null
                            : () async {
                                update(() {
                                  _confirming = true;
                                  _confirmationError = null;
                                });
                                try {
                                  final result = await ref
                                      .read(projectRepositoryProvider)
                                      .confirmMailerPublication(
                                          widget.projectRef,
                                          kind,
                                          current['version'] as int,
                                          current['draft_digest'] as String,
                                          password.text);
                                  if (dialogContext.mounted) {
                                    Navigator.pop(dialogContext, result);
                                  }
                                } catch (e) {
                                  if (dialogContext.mounted) {
                                    update(() =>
                                        _confirmationError = e.toString());
                                  }
                                } finally {
                                  if (dialogContext.mounted) {
                                    update(() => _confirming = false);
                                  } else {
                                    _confirming = false;
                                  }
                                }
                              },
                        child: Text(sending
                            ? 'Confirmando...'
                            : 'Confirmar publicação')),
                  ],
                );
              }));
    } finally {
      password.clear();
      // Let the dialog finish its closing animation before disposing its field.
      Future<void>.delayed(const Duration(milliseconds: 300), password.dispose);
      _confirming = false;
      _confirmationError = null;
    }
    if (token == null || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
      _message = null;
    });
    try {
      final data = await ref
          .read(projectRepositoryProvider)
          .mailerTemplatesRequest(widget.projectRef,
              kind: kind,
              operation: 'publish',
              method: 'POST',
              stepUpToken: token,
              body: {
            'version': current['version'],
            'draft_digest': current['draft_digest']
          });
      if (!mounted) return;
      setState(() {
        _templates[_templates.indexWhere((row) => row['kind'] == kind)] = data;
        _editor.text = data['body'] as String;
        _dirty = false;
        _preview = null;
        _message =
            'Template publicado. Os próximos envios usarão a alteração após a renovação do cache (até 1 minuto).';
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  bool _confirming = false;
  String? _confirmationError;

  Future<void> _history() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await ref
          .read(projectRepositoryProvider)
          .mailerTemplatesRequest(widget.projectRef,
              kind: _kind, operation: 'history');
      if (!mounted) return;
      final versions = (data['versions'] as List).cast<Map<String, dynamic>>();
      setState(() => _busy = false);
      final selected = await showDialog<Map<String, dynamic>>(
          context: context,
          builder: (context) => AlertDialog(
                title: const Text('Histórico do template'),
                content: SizedBox(
                  width: 560,
                  height: 360,
                  child: versions.isEmpty
                      ? const Text('Nenhuma personalização registrada.')
                      : ListView(
                          children: versions
                              .map((row) => ListTile(
                                    title: Text(
                                        'Versão ${row['version']} · ${_historyLabels[row['action']] ?? 'Versão registrada'}'),
                                    subtitle: Text(
                                        '${row['updated_at']}\n${row['updated_by']}'),
                                    trailing: const Icon(Icons.restore),
                                    onTap: () => Navigator.pop(context, row),
                                  ))
                              .toList()),
                ),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Fechar'))
                ],
              ));
      if (!mounted || selected == null) return;
      if (_dirty &&
          !await _confirm('Substituir o HTML editado?',
              'A versão escolhida será carregada no editor.')) {
        return;
      }
      if (!mounted) return;
      setState(() => _busy = true);
      final historical = await ref
          .read(projectRepositoryProvider)
          .mailerTemplatesRequest(widget.projectRef,
              kind: _kind, operation: 'history/${selected['version']}');
      if (!mounted) return;
      setState(() {
        _editor.text =
            (historical['body'] ?? _current['default_body']) as String;
        _dirty = true;
        _preview = null;
        _message =
            'Versão ${selected['version']} carregada. Revise e salve para publicar.';
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _importHtml() async {
    try {
      final body = await pickMailerHtml();
      if (body == null || !mounted) return;
      if (_dirty &&
          !await _confirm('Substituir o HTML editado?',
              'O arquivo será carregado no editor. Revise e salve para publicar.')) {
        return;
      }
      if (!mounted) return;
      setState(() {
        _editor.text = body;
        _dirty = true;
        _preview = null;
        _error = null;
        _message = 'HTML importado. Confira a prévia e salve para publicar.';
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_templates.isEmpty) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (_busy) const LinearProgressIndicator(),
        if (_error != null)
          Text(_error!, style: const TextStyle(color: SupabaseColors.error)),
        if (!_busy)
          TextButton(onPressed: _load, child: const Text('Tentar novamente')),
      ]);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('Templates de e-mail',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
      const SizedBox(height: 8),
      const Text(
          'Edite e salve um rascunho. Os envios só mudam após publicar com a confirmação da sua identidade.'),
      const SizedBox(height: 16),
      DropdownButton<String>(
        value: _kind,
        isExpanded: true,
        items: _labels.entries
            .map((entry) =>
                DropdownMenuItem(value: entry.key, child: Text(entry.value)))
            .toList(),
        onChanged: _busy
            ? null
            : (value) {
                if (value != null) _changeKind(value);
              },
      ),
      const SizedBox(height: 8),
      Text(
          'Publicado: ${_current['source'] == 'default' ? 'padrão da plataforma' : 'personalizado'} · versão ${_current['published_version'] ?? 0}${_current['has_draft'] == true ? ' · rascunho pendente' : ''}${_dirty ? ' · alterações não salvas' : ''}'),
      if (_allowedOrigins.isNotEmpty)
        Text('Domínios aprovados: ${_allowedOrigins.join(', ')}'),
      const SizedBox(height: 12),
      const SelectableText(
          'Variáveis no texto: .Token, .Email, .NewEmail, .Data. Para o link de autenticação, use {{ .ConfirmationURL }}. Imagens precisam de HTTPS em um domínio aprovado e não podem conter variáveis.'),
      const SizedBox(height: 12),
      TextField(
        controller: _editor,
        enabled: !_busy,
        minLines: 12,
        maxLines: 20,
        keyboardType: TextInputType.multiline,
        style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
        decoration: const InputDecoration(
            labelText: 'HTML do e-mail (até 1 MB)',
            border: OutlineInputBorder()),
        onChanged: (_) => setState(() {
          _dirty = true;
          _preview = null;
          _message = null;
        }),
      ),
      const SizedBox(height: 12),
      Wrap(spacing: 8, runSpacing: 8, children: [
        TextButton.icon(
            onPressed: _busy ? null : _importHtml,
            icon: const Icon(Icons.upload_file),
            label: const Text('Importar HTML')),
        FilledButton.icon(
            onPressed: _busy || (!_dirty && _current['has_draft'] != true)
                ? null
                : () => _act('save'),
            icon: const Icon(Icons.save_outlined),
            label: const Text('Salvar rascunho')),
        FilledButton.icon(
            onPressed: _busy || _dirty || _current['has_draft'] != true
                ? null
                : _publish,
            icon: const Icon(Icons.publish),
            label: const Text('Publicar')),
        OutlinedButton.icon(
            onPressed: _busy ? null : () => _act('preview'),
            icon: const Icon(Icons.visibility_outlined),
            label: const Text('Prévia')),
        TextButton(
            onPressed: _busy || _current['source'] == 'default'
                ? null
                : () => _act('reset'),
            child: const Text('Preparar padrão')),
        TextButton(
            onPressed: _busy ? null : _history, child: const Text('Histórico')),
        TextButton(
            onPressed: _busy
                ? null
                : () async {
                    if (_dirty &&
                        !await _confirm('Descartar alterações?',
                            'Recarregar substitui o HTML editado pela versão salva.')) {
                      return;
                    }
                    if (mounted) _load();
                  },
            child: const Text('Recarregar')),
      ]),
      if (_busy) const LinearProgressIndicator(),
      if (_error != null)
        Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(_error!,
                style: const TextStyle(color: SupabaseColors.error))),
      if (_message != null)
        Padding(
            padding: const EdgeInsets.only(top: 12), child: Text(_message!)),
      if (_preview != null) ...[
        const SizedBox(height: 16),
        const Text('Prévia com dados de exemplo'),
        const SizedBox(height: 8),
        SizedBox(height: 400, child: MailerPreview(html: _preview!)),
      ],
    ]);
  }
}
