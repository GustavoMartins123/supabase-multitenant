import 'dart:math';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class NewProjectDialog extends StatefulWidget {
  const NewProjectDialog({super.key});

  @override
  State<NewProjectDialog> createState() => _NewProjectDialogState();
}

class _NewProjectDialogState extends State<NewProjectDialog> {
  final _ctrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  final _rand = Random.secure();

  /* Regras base (3–40 chars) */
  static final _regex = RegExp(r'^[a-z_][a-z0-9_]{2,40}$');
  String _crop(String s) => s.length > 40 ? s.substring(0, 40) : s;
  static const _reserved = <String>{
    'select','from','where','insert','update','delete','table',
    'create','drop','join','group','order','limit','into','index',
    'view','trigger','procedure','function','database','schema',
    'primary','foreign','key','constraint','unique','null','not',
    'and','or','in','like','between','exists','having','union',
    'inner','left','right','outer','cross','on','as','case','when',
    'then','else','end','if','while','for','begin','commit','rollback'
  };

  /* Lista de prefixos e sufixos comuns para projetos */
  static const _prefixes = <String>[
    'app', 'web', 'api', 'mobile', 'desktop', 'backend', 'frontend',
    'system', 'tool', 'lib', 'framework', 'service', 'micro', 'mini'
  ];

  static const _suffixes = <String>[
    'app', 'tool', 'system', 'service', 'api', 'web', 'mobile',
    'client', 'server', 'core', 'lib', 'kit', 'hub', 'pro'
  ];

  /* gera string aleatória abc123 de 4-6 chars */
  String _randString([int length = 6]) {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    return List.generate(length, (_) => chars[_rand.nextInt(chars.length)]).join();
  }

  /* normaliza texto de entrada */
  String _normalize(String input) {
    return input
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9_]'), '_')
        .replaceAll(RegExp(r'_+'), '_') // remove underscores duplos
        .replaceAll(RegExp(r'^_+|_+$'), ''); // remove underscores no início/fim
  }

  /* gera sugestões melhoradas */
  List<String> _suggestions(String raw) {
    final base = _normalize(raw);
    if (base.isEmpty) return _getDefaultSuggestions();

    final Set<String> suggestions = <String>{};

    void addIfValid(String s) {
      final normalized = _crop(_normalize(s));
      if (normalized.isNotEmpty &&
          _regex.hasMatch(normalized) &&
          !_reserved.contains(normalized)) {
        suggestions.add(normalized);
      }
    }

    if (!_reserved.contains(base)) addIfValid(base);

    final today = DateFormat('ddMMyy').format(DateTime.now());
    final year = DateFormat('yyyy').format(DateTime.now());
    addIfValid('${base}_$today');
    addIfValid('${base}_v1');
    addIfValid('${base}_$year');
    addIfValid('${base}_dev');
    addIfValid('${base}_prod');
    addIfValid('${base}_test');

    if (base.length <= 10) {
      for (final prefix in _prefixes.take(3)) {
        addIfValid('${prefix}_$base');
      }
      for (final suffix in _suffixes.take(3)) {
        addIfValid('${base}_$suffix');
      }
    }

    addIfValid('${base}_${_randString(4)}');
    addIfValid('${base}_${_rand.nextInt(999) + 1}');

    if (suggestions.length < 8) {
      addIfValid('my_$base');
      addIfValid('${base}_project');
      addIfValid('${base}_app');
    }

    return suggestions.take(10).toList();
  }



  /* sugestões padrão quando input está vazio */
  List<String> _getDefaultSuggestions() {
    final suggestions = <String>[];
    final today = DateFormat('ddMMyy').format(DateTime.now());

    suggestions.addAll([
      'meu_projeto',
      'projeto_$today',
      'idr_${_randString(4)}',
      'sistema_novo',
      'app_${_randString(4)}',
    ]);

    return suggestions;
  }

  String? _validate(String? v) {
    if (v == null || v.trim().isEmpty) return 'Informe um nome';
    final txt = _normalize(v);
    if (txt.isEmpty) return 'Nome inválido';
    if (!_regex.hasMatch(txt)) return 'Use minúsculas, números ou "_" (3-40 caracteres)';
    if (_reserved.contains(txt)) return 'Nome reservado — escolha outro.';
    return null;
  }

  void _submit() {
    if (_formKey.currentState!.validate()) {
      Navigator.pop(context, _normalize(_ctrl.text));
    }
  }

  void _selectSuggestion(String suggestion) {
    setState(() {
      _ctrl.text = suggestion;
      _ctrl.selection = TextSelection.fromPosition(
        TextPosition(offset: suggestion.length),
      );
    });
    // Validar após selecionar
    _formKey.currentState?.validate();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Novo Projeto'),
      content: SizedBox(
        width: MediaQuery.of(context).size.width * 0.8,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Autocomplete<String>(
                optionsBuilder: (textEditingValue) {
                  return _suggestions(textEditingValue.text);
                },
                fieldViewBuilder: (context, controller, focusNode, onSubmitted) {
                  // Sincronizar com nosso controller principal
                  if (controller.text != _ctrl.text) {
                    controller.text = _ctrl.text;
                    controller.selection = _ctrl.selection;
                  }

                  return TextFormField(
                    controller: controller,
                    focusNode: focusNode,
                    decoration: const InputDecoration(
                      labelText: 'Nome do projeto',
                      hintText: 'ex.: meu_projeto',
                      border: OutlineInputBorder(),
                    ),
                    validator: _validate,
                    onChanged: (value) {
                      // Sincronizar mudanças
                      _ctrl.text = value;
                      _ctrl.selection = controller.selection;
                    },
                    onFieldSubmitted: (_) => _submit(),
                  );
                },
                onSelected: (String selection) {
                  _selectSuggestion(selection);
                },
                optionsViewBuilder: (context, onSelected, options) {
                  return Align(
                    alignment: Alignment.topLeft,
                    child: Material(
                      elevation: 8,
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        constraints: BoxConstraints(
                          maxHeight: 200,
                          maxWidth: MediaQuery.of(context).size.width * 0.8,
                        ),
                        child: ListView.builder(
                          padding: EdgeInsets.zero,
                          shrinkWrap: true,
                          itemCount: options.length,
                          itemBuilder: (context, index) {
                            final option = options.elementAt(index);
                            return InkWell(
                              onTap: () => onSelected(option),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 16,
                                    vertical: 12
                                ),
                                child: Row(
                                  children: [
                                    const Icon(
                                        Icons.code,
                                        size: 16,
                                        color: Colors.grey
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        option,
                                        style: const TextStyle(fontSize: 14),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                  );
                },
              ),
              const SizedBox(height: 8),
              Text(
                'Dica: Use apenas letras minúsculas, números e underscore (_)',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Colors.grey[600],
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        ElevatedButton(
          onPressed: _submit,
          child: const Text('Criar'),
        ),
      ],
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }
}