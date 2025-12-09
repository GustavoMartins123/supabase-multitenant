import 'dart:math';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class NewProjectDialog extends StatefulWidget {
  const NewProjectDialog({super.key});

  @override
  State<NewProjectDialog> createState() => _NewProjectDialogState();
}

class _NewProjectDialogState extends State<NewProjectDialog>
    with SingleTickerProviderStateMixin {
  final _ctrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  final _rand = Random.secure();
  late AnimationController _animController;
  late Animation<double> _scaleAnimation;

  static final _regex = RegExp(r'^[a-z_][a-z0-9_]{2,40}$');
  String _crop(String s) => s.length > 40 ? s.substring(0, 40) : s;

  static const _reserved = <String>{
    'select', 'from', 'where', 'insert', 'update', 'delete', 'table',
    'create', 'drop', 'join', 'group', 'order', 'limit', 'into', 'index',
    'view', 'trigger', 'procedure', 'function', 'database', 'schema',
    'primary', 'foreign', 'key', 'constraint', 'unique', 'null', 'not',
    'and', 'or', 'in', 'like', 'between', 'exists', 'having', 'union',
    'inner', 'left', 'right', 'outer', 'cross', 'on', 'as', 'case', 'when',
    'then', 'else', 'end', 'if', 'while', 'for', 'begin', 'commit', 'rollback'
  };

  static const _prefixes = <String>[
    'app', 'web', 'api', 'mobile', 'desktop', 'backend', 'frontend',
    'system', 'tool', 'lib', 'framework', 'service', 'micro', 'mini'
  ];

  static const _suffixes = <String>[
    'app', 'tool', 'system', 'service', 'api', 'web', 'mobile',
    'client', 'server', 'core', 'lib', 'kit', 'hub', 'pro'
  ];

  @override
  void initState() {
    super.initState();
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
    _ctrl.dispose();
    _animController.dispose();
    super.dispose();
  }

  String _randString([int length = 6]) {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    return List.generate(length, (_) => chars[_rand.nextInt(chars.length)]).join();
  }

  String _normalize(String input) {
    return input
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9_]'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
  }

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
    _formKey.currentState?.validate();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scaleAnimation,
      child: Dialog(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: Container(
          constraints: BoxConstraints(
            maxWidth: 520,
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          decoration: BoxDecoration(
            color: SupabaseColors.bg200,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: SupabaseColors.border),
          ),
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: SupabaseColors.brand.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Icon(
                            Icons.add_rounded,
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
                                'Novo Projeto',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  color: SupabaseColors.textPrimary,
                                ),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Configure seu novo projeto',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: SupabaseColors.textMuted,
                                ),
                              ),
                            ],
                          ),
                        ),
                        _CloseBtn(onPressed: () => Navigator.pop(context)),
                      ],
                    ),

                    const SizedBox(height: 24),
                    const Divider(color: SupabaseColors.border, height: 1),
                    const SizedBox(height: 24),

                    const Text(
                      'Nome do Projeto',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: SupabaseColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 8),

                    Autocomplete<String>(
                      optionsBuilder: (textEditingValue) {
                        return _suggestions(textEditingValue.text);
                      },
                      fieldViewBuilder: (context, controller, focusNode, onSubmitted) {
                        if (controller.text != _ctrl.text) {
                          controller.text = _ctrl.text;
                          controller.selection = _ctrl.selection;
                        }

                        return TextFormField(
                          controller: controller,
                          focusNode: focusNode,
                          decoration: InputDecoration(
                            hintText: 'ex.: meu_projeto_incrivel',
                            hintStyle: const TextStyle(
                              color: SupabaseColors.textMuted,
                              fontSize: 13,
                            ),
                            prefixIcon: const Icon(
                              Icons.folder_rounded,
                              color: SupabaseColors.textMuted,
                              size: 18,
                            ),
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
                            errorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(6),
                              borderSide: const BorderSide(color: SupabaseColors.error),
                            ),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                          ),
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: SupabaseColors.textPrimary,
                          ),
                          validator: _validate,
                          onChanged: (value) {
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
                            borderRadius: BorderRadius.circular(6),
                            color: SupabaseColors.surface300,
                            child: Container(
                              constraints: const BoxConstraints(maxHeight: 240, maxWidth: 400),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: SupabaseColors.border),
                              ),
                              child: ListView.builder(
                                padding: const EdgeInsets.symmetric(vertical: 4),
                                shrinkWrap: true,
                                itemCount: options.length,
                                itemBuilder: (context, index) {
                                  final option = options.elementAt(index);
                                  return InkWell(
                                    onTap: () => onSelected(option),
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                      child: Row(
                                        children: [
                                          const Icon(
                                            Icons.lightbulb_outline_rounded,
                                            size: 14,
                                            color: SupabaseColors.brand,
                                          ),
                                          const SizedBox(width: 10),
                                          Expanded(
                                            child: Text(
                                              option,
                                              style: const TextStyle(
                                                fontSize: 12,
                                                fontFamily: 'monospace',
                                                color: SupabaseColors.textSecondary,
                                              ),
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

                    const SizedBox(height: 16),

                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: SupabaseColors.info.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: SupabaseColors.info.withOpacity(0.2)),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.info_outline_rounded,
                            color: SupabaseColors.info,
                            size: 16,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: const [
                                Text(
                                  'Regras de nomenclatura',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: SupabaseColors.textPrimary,
                                  ),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  '• Apenas letras minúsculas, números e underscore\n'
                                      '• Deve começar com letra ou underscore\n'
                                      '• Entre 3 e 40 caracteres',
                                  style: TextStyle(
                                    fontSize: 11,
                                    height: 1.4,
                                    color: SupabaseColors.textMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 24),
                    const Divider(color: SupabaseColors.border, height: 1),
                    const SizedBox(height: 16),

                    Row(
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
                          label: 'Criar Projeto',
                          icon: Icons.rocket_launch_rounded,
                          onPressed: _submit,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
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
  const _PrimaryButton({required this.label, required this.icon, required this.onPressed});
  final String label;
  final IconData icon;
  final VoidCallback onPressed;

  @override
  State<_PrimaryButton> createState() => _PrimaryButtonState();
}

class _PrimaryButtonState extends State<_PrimaryButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          color: _hover ? SupabaseColors.brandLight : SupabaseColors.brand,
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
                  Icon(widget.icon, size: 16, color: SupabaseColors.bg100),
                  const SizedBox(width: 8),
                  Text(
                    widget.label,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: SupabaseColors.bg100,
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