import 'dart:math';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class NewProjectDialog extends StatefulWidget {
  const NewProjectDialog({super.key});

  @override
  State<NewProjectDialog> createState() => _NewProjectDialogState();
}

class _NewProjectDialogState extends State<NewProjectDialog> with SingleTickerProviderStateMixin {
  final _ctrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  final _rand = Random.secure();
  late AnimationController _animController;
  late Animation<double> _scaleAnimation;

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

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _scaleAnimation = CurvedAnimation(
      parent: _animController,
      curve: Curves.easeOutBack,
    );
    _animController.forward();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _animController.dispose();
    super.dispose();
  }

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
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
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
    _formKey.currentState?.validate();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final isDark = t.brightness == Brightness.dark;

    return ScaleTransition(
      scale: _scaleAnimation,
      child: Dialog(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: Container(
          constraints: BoxConstraints(
            maxWidth: 600,
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: isDark
                  ? [
                const Color(0xFF1A1F2E),
                const Color(0xFF12161F),
              ]
                  : [
                Colors.white,
                Colors.grey[50]!,
              ],
            ),
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: isDark ? Colors.white.withOpacity(0.1) : Colors.black.withOpacity(0.08),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: isDark ? Colors.black.withOpacity(0.5) : Colors.black.withOpacity(0.15),
                blurRadius: 40,
                offset: const Offset(0, 20),
              ),
            ],
          ),
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [
                                t.colorScheme.primary,
                                t.colorScheme.secondary,
                              ],
                            ),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: t.colorScheme.primary.withOpacity(0.3),
                                blurRadius: 16,
                                offset: const Offset(0, 8),
                              ),
                            ],
                          ),
                          child: Icon(
                            Icons.create_new_folder_rounded,
                            color: Colors.white,
                            size: 28,
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Novo Projeto',
                                style: TextStyle(
                                  fontSize: 26,
                                  fontWeight: FontWeight.bold,
                                  color: isDark ? Colors.white : Colors.black87,
                                  letterSpacing: -0.5,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Configure seu novo projeto',
                                style: TextStyle(
                                  fontSize: 14,
                                  color: isDark ? Colors.white54 : Colors.black54,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 32),
                    Autocomplete<String>(
                      optionsBuilder: (textEditingValue) {
                        return _suggestions(textEditingValue.text);
                      },
                      fieldViewBuilder: (context, controller, focusNode, onSubmitted) {
                        if (controller.text != _ctrl.text) {
                          controller.text = _ctrl.text;
                          controller.selection = _ctrl.selection;
                        }

                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Nome do Projeto',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.5,
                                color: isDark ? Colors.white70 : Colors.black87,
                              ),
                            ),
                            const SizedBox(height: 12),
                            TextFormField(
                              controller: controller,
                              focusNode: focusNode,
                              decoration: InputDecoration(
                                hintText: 'ex.: meu_projeto_incrivel',
                                hintStyle: TextStyle(
                                  color: isDark ? Colors.white24 : Colors.black26,
                                ),
                                prefixIcon: Icon(
                                  Icons.edit_rounded,
                                  color: isDark ? Colors.white54 : Colors.black54,
                                  size: 20,
                                ),
                                filled: true,
                                fillColor: isDark
                                    ? Colors.white.withOpacity(0.05)
                                    : Colors.grey[100],
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(16),
                                  borderSide: BorderSide.none,
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(16),
                                  borderSide: BorderSide(
                                    color: isDark
                                        ? Colors.white.withOpacity(0.08)
                                        : Colors.black.withOpacity(0.08),
                                    width: 1,
                                  ),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(16),
                                  borderSide: BorderSide(
                                    color: t.colorScheme.primary,
                                    width: 2,
                                  ),
                                ),
                                errorBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(16),
                                  borderSide: BorderSide(
                                    color: t.colorScheme.error,
                                    width: 1,
                                  ),
                                ),
                                focusedErrorBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(16),
                                  borderSide: BorderSide(
                                    color: t.colorScheme.error,
                                    width: 2,
                                  ),
                                ),
                                contentPadding: const EdgeInsets.all(20),
                              ),
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w500,
                                color: isDark ? Colors.white : Colors.black87,
                              ),
                              validator: _validate,
                              onChanged: (value) {
                                _ctrl.text = value;
                                _ctrl.selection = controller.selection;
                              },
                              onFieldSubmitted: (_) => _submit(),
                            ),
                          ],
                        );
                      },
                      onSelected: (String selection) {
                        _selectSuggestion(selection);
                      },
                      optionsViewBuilder: (context, onSelected, options) {
                        return Align(
                          alignment: Alignment.topLeft,
                          child: Material(
                            elevation: 16,
                            borderRadius: BorderRadius.circular(20),
                            color: isDark ? const Color(0xFF1E2330) : Colors.white,
                            child: Container(
                              constraints: BoxConstraints(
                                maxHeight: 280,
                                maxWidth: MediaQuery.of(context).size.width * 0.8,
                              ),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(
                                  color: isDark
                                      ? Colors.white.withOpacity(0.1)
                                      : Colors.black.withOpacity(0.08),
                                ),
                              ),
                              child: ListView.builder(
                                padding: const EdgeInsets.symmetric(vertical: 8),
                                shrinkWrap: true,
                                itemCount: options.length,
                                itemBuilder: (context, index) {
                                  final option = options.elementAt(index);
                                  return InkWell(
                                    onTap: () => onSelected(option),
                                    borderRadius: BorderRadius.circular(12),
                                    child: Container(
                                      margin: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                        vertical: 2,
                                      ),
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 16,
                                        vertical: 14,
                                      ),
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Row(
                                        children: [
                                          Container(
                                            padding: const EdgeInsets.all(8),
                                            decoration: BoxDecoration(
                                              color: t.colorScheme.primary.withOpacity(0.15),
                                              borderRadius: BorderRadius.circular(8),
                                            ),
                                            child: Icon(
                                              Icons.lightbulb_outline_rounded,
                                              size: 16,
                                              color: t.colorScheme.primary,
                                            ),
                                          ),
                                          const SizedBox(width: 12),
                                          Expanded(
                                            child: Text(
                                              option,
                                              style: TextStyle(
                                                fontSize: 14,
                                                fontWeight: FontWeight.w500,
                                                fontFamily: 'monospace',
                                                color: isDark ? Colors.white60 : Colors.black87,
                                              ),
                                            ),
                                          ),
                                          Icon(
                                            Icons.arrow_forward_rounded,
                                            size: 16,
                                            color: isDark ? Colors.white38 : Colors.black38,
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
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: t.colorScheme.primary.withOpacity(0.08),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: t.colorScheme.primary.withOpacity(0.2),
                          width: 1,
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.info_outline_rounded,
                            color: t.colorScheme.primary,
                            size: 20,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Regras de nomenclatura',
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: isDark ? Colors.white60 : Colors.black87,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  '• Apenas letras minúsculas, números e underscore (_)\n'
                                      '• Deve começar com letra ou underscore\n'
                                      '• Entre 3 e 40 caracteres\n'
                                      '• Palavras reservadas não são permitidas',
                                  style: TextStyle(
                                    fontSize: 12,
                                    height: 1.5,
                                    color: isDark ? Colors.white60 : Colors.black54,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 32),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 24,
                              vertical: 16,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                          child: Text(
                            'Cancelar',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              color: isDark ? Colors.white60 : Colors.black54,
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [
                                t.colorScheme.primary,
                                t.colorScheme.secondary,
                              ],
                            ),
                            borderRadius: BorderRadius.circular(12),
                            boxShadow: [
                              BoxShadow(
                                color: t.colorScheme.primary.withOpacity(0.4),
                                blurRadius: 16,
                                offset: const Offset(0, 8),
                              ),
                            ],
                          ),
                          child: ElevatedButton(
                            onPressed: _submit,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.transparent,
                              shadowColor: Colors.transparent,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 32,
                                vertical: 16,
                              ),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.rocket_launch_rounded, size: 20),
                                SizedBox(width: 8),
                                Text(
                                  'Criar Projeto',
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                    color: Colors.black87,
                                  ),
                                ),
                              ],
                            ),
                          ),
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
