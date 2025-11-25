import 'dart:math';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class DuplicateProjectDialog extends StatefulWidget {
  final String originalProjectName;

  const DuplicateProjectDialog({
    super.key,
    required this.originalProjectName,
  });

  @override
  State<DuplicateProjectDialog> createState() => _DuplicateProjectDialogState();
}

class _DuplicateProjectDialogState extends State<DuplicateProjectDialog> with SingleTickerProviderStateMixin {
  final _ctrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  final _rand = Random.secure();
  late AnimationController _animController;
  late Animation<double> _scaleAnimation;
  bool _copyData = false;  // Flag para copiar dados

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

  @override
  void initState() {
    super.initState();

    // Define nome padrão: nome_original_copy
    _ctrl.text = _crop('${widget.originalProjectName}_copy');

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

  String _normalize(String input) {
    return input
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9_]'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
  }

  String? _validate(String? v) {
    if (v == null || v.trim().isEmpty) return 'Informe um nome';
    final txt = _normalize(v);
    if (txt.isEmpty) return 'Nome inválido';
    if (!_regex.hasMatch(txt)) return 'Use minúsculas, números ou "_" (3-40 caracteres)';
    if (_reserved.contains(txt)) return 'Nome reservado — escolha outro.';
    if (txt == widget.originalProjectName) return 'O nome deve ser diferente do original';
    return null;
  }

  void _submit() {
    if (_formKey.currentState!.validate()) {
      Navigator.pop(context, {
        'name': _normalize(_ctrl.text),
        'copy_data': _copyData,
      });
    }
  }

  List<String> _getSuggestions() {
    final base = widget.originalProjectName;
    final suggestions = <String>[];
    final today = DateFormat('ddMMyy').format(DateTime.now());

    suggestions.addAll([
      _crop('${base}_copy'),
      _crop('${base}_backup'),
      _crop('${base}_$today'),
      _crop('${base}_v2'),
      _crop('${base}_clone'),
    ]);

    return suggestions.where((s) =>
    s.isNotEmpty &&
        _regex.hasMatch(s) &&
        !_reserved.contains(s)
    ).toList();
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
          constraints: const BoxConstraints(maxWidth: 650),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: isDark
                  ? [const Color(0xFF1A1F2E), const Color(0xFF12161F)]
                  : [Colors.white, Colors.grey[50]!],
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
                                Colors.blue.shade400,
                                Colors.cyan.shade400,
                              ],
                            ),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.blue.withOpacity(0.3),
                                blurRadius: 16,
                                offset: const Offset(0, 8),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.content_copy_rounded,
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
                                'Duplicar Projeto',
                                style: TextStyle(
                                  fontSize: 26,
                                  fontWeight: FontWeight.bold,
                                  color: isDark ? Colors.white : Colors.black87,
                                  letterSpacing: -0.5,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Criar cópia com novo nome',
                                style: TextStyle(
                                  fontSize: 14,
                                  color: isDark ? Colors.white54 : Colors.black54,
                                ),
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          onPressed: () => Navigator.pop(context),
                          icon: Icon(
                            Icons.close_rounded,
                            color: isDark ? Colors.white70 : Colors.black54,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 32),

                    // Mostra projeto original
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: isDark
                            ? Colors.white.withOpacity(0.05)
                            : Colors.grey[100],
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: isDark
                              ? Colors.white.withOpacity(0.08)
                              : Colors.black.withOpacity(0.08),
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  t.colorScheme.primary.withOpacity(0.2),
                                  t.colorScheme.secondary.withOpacity(0.2),
                                ],
                              ),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(
                              Icons.folder_rounded,
                              color: t.colorScheme.primary,
                              size: 20,
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'PROJETO ORIGINAL',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1.2,
                                    color: isDark ? Colors.white38 : Colors.black38,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  widget.originalProjectName,
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                    fontFamily: 'monospace',
                                    color: isDark ? Colors.white : Colors.black87,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 24),

                    // Campo nome do novo projeto
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Nome do Novo Projeto',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                            color: isDark ? Colors.white70 : Colors.black87,
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _ctrl,
                          decoration: InputDecoration(
                            hintText: 'ex.: ${widget.originalProjectName}_copy',
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
                            fontFamily: 'monospace',
                            color: isDark ? Colors.white : Colors.black87,
                          ),
                          validator: _validate,
                          onFieldSubmitted: (_) => _submit(),
                        ),
                      ],
                    ),

                    const SizedBox(height: 20),

                    // Sugestões rápidas
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.lightbulb_outline_rounded,
                              size: 16,
                              color: isDark ? Colors.white54 : Colors.black54,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Sugestões rápidas',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: isDark ? Colors.white54 : Colors.black54,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: _getSuggestions().map((suggestion) {
                            final isSelected = _ctrl.text == suggestion;
                            return InkWell(
                              onTap: () => _selectSuggestion(suggestion),
                              borderRadius: BorderRadius.circular(12),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 14,
                                  vertical: 8,
                                ),
                                decoration: BoxDecoration(
                                  gradient: isSelected
                                      ? LinearGradient(
                                    colors: [
                                      t.colorScheme.primary.withOpacity(0.2),
                                      t.colorScheme.secondary.withOpacity(0.2),
                                    ],
                                  )
                                      : null,
                                  color: isSelected
                                      ? null
                                      : (isDark
                                      ? Colors.white.withOpacity(0.05)
                                      : Colors.grey[200]),
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(
                                    color: isSelected
                                        ? t.colorScheme.primary.withOpacity(0.4)
                                        : (isDark
                                        ? Colors.white.withOpacity(0.08)
                                        : Colors.black.withOpacity(0.08)),
                                  ),
                                ),
                                child: Text(
                                  suggestion,
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontFamily: 'monospace',
                                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                                    color: isSelected
                                        ? t.colorScheme.primary
                                        : (isDark ? Colors.white70 : Colors.black87),
                                  ),
                                ),
                              ),
                            );
                          }).toList(),
                        ),
                      ],
                    ),

                    const SizedBox(height: 24),

                    // Checkbox para copiar dados
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: isDark
                            ? Colors.white.withOpacity(0.05)
                            : Colors.grey[100],
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: _copyData
                              ? t.colorScheme.primary.withOpacity(0.3)
                              : (isDark
                              ? Colors.white.withOpacity(0.08)
                              : Colors.black.withOpacity(0.08)),
                        ),
                      ),
                      child: Row(
                        children: [
                          Checkbox(
                            value: _copyData,
                            onChanged: (val) {
                              setState(() {
                                _copyData = val ?? false;
                              });
                            },
                            activeColor: t.colorScheme.primary,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Copiar dados das tabelas',
                                  style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                    color: isDark ? Colors.white70 : Colors.black87,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Incluir todos os registros existentes no novo projeto',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: isDark ? Colors.white54 : Colors.black54,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 20),

                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.08),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: Colors.blue.withOpacity(0.2),
                          width: 1,
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            Icons.info_outline_rounded,
                            color: Colors.blue,
                            size: 20,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'O que será duplicado',
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: isDark ? Colors.white70 : Colors.black87,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  _copyData
                                      ? '• Estrutura do banco de dados\n'
                                      '• Configurações do projeto\n'
                                      '• Schemas e tabelas\n'
                                      '• Políticas de segurança\n'
                                      '• Dados de todas as tabelas ✓'
                                      : '• Estrutura do banco de dados\n'
                                      '• Configurações do projeto\n'
                                      '• Schemas e tabelas\n'
                                      '• Políticas de segurança',
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
                                Colors.blue.shade400,
                                Colors.cyan.shade400,
                              ],
                            ),
                            borderRadius: BorderRadius.circular(12),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.blue.withOpacity(0.4),
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
                                Icon(Icons.content_copy_rounded, size: 20),
                                SizedBox(width: 8),
                                Text(
                                  'Duplicar Projeto',
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.bold,
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
