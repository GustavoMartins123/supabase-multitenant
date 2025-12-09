import 'dart:math';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class DuplicateProjectDialog extends StatefulWidget {
  final String originalProjectName;

  const DuplicateProjectDialog({
    super.key,
    required this.originalProjectName,
  });

  @override
  State<DuplicateProjectDialog> createState() => _DuplicateProjectDialogState();
}

class _DuplicateProjectDialogState extends State<DuplicateProjectDialog>
    with SingleTickerProviderStateMixin {
  final _ctrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  late AnimationController _animController;
  late Animation<double> _scaleAnimation;
  bool _copyData = false;

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

  @override
  void initState() {
    super.initState();
    _ctrl.text = _crop('${widget.originalProjectName}_copy');

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

    return suggestions
        .where((s) => s.isNotEmpty && _regex.hasMatch(s) && !_reserved.contains(s))
        .toList();
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
          constraints: const BoxConstraints(maxWidth: 520),
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
                            color: SupabaseColors.info.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Icon(
                            Icons.copy_rounded,
                            color: SupabaseColors.info,
                            size: 20,
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Duplicar Projeto',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  color: SupabaseColors.textPrimary,
                                ),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Criar cópia com novo nome',
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
                    const SizedBox(height: 20),

                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: SupabaseColors.bg300,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: SupabaseColors.border),
                      ),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: SupabaseColors.brand.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: const Icon(
                              Icons.folder_rounded,
                              color: SupabaseColors.brand,
                              size: 16,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'PROJETO ORIGINAL',
                                  style: TextStyle(
                                    fontSize: 9,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1,
                                    color: SupabaseColors.textMuted,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  widget.originalProjectName,
                                  style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    fontFamily: 'monospace',
                                    color: SupabaseColors.textPrimary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 20),

                    const Text(
                      'Nome do Novo Projeto',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: SupabaseColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 8),

                    TextFormField(
                      controller: _ctrl,
                      decoration: InputDecoration(
                        hintText: 'ex.: ${widget.originalProjectName}_copy',
                        hintStyle: const TextStyle(
                          color: SupabaseColors.textMuted,
                          fontSize: 13,
                        ),
                        prefixIcon: const Icon(
                          Icons.edit_rounded,
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
                        fontFamily: 'monospace',
                        color: SupabaseColors.textPrimary,
                      ),
                      validator: _validate,
                      onFieldSubmitted: (_) => _submit(),
                    ),

                    const SizedBox(height: 16),

                    Row(
                      children: const [
                        Icon(Icons.lightbulb_outline_rounded, size: 14, color: SupabaseColors.textMuted),
                        SizedBox(width: 6),
                        Text(
                          'Sugestões',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: SupabaseColors.textMuted),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: _getSuggestions().map((suggestion) {
                        final isSelected = _ctrl.text == suggestion;
                        return InkWell(
                          onTap: () => _selectSuggestion(suggestion),
                          borderRadius: BorderRadius.circular(6),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? SupabaseColors.brand.withOpacity(0.15)
                                  : SupabaseColors.bg300,
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: isSelected
                                    ? SupabaseColors.brand.withOpacity(0.4)
                                    : SupabaseColors.border,
                              ),
                            ),
                            child: Text(
                              suggestion,
                              style: TextStyle(
                                fontSize: 11,
                                fontFamily: 'monospace',
                                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                                color: isSelected ? SupabaseColors.brand : SupabaseColors.textSecondary,
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),

                    const SizedBox(height: 20),

                    InkWell(
                      onTap: () => setState(() => _copyData = !_copyData),
                      borderRadius: BorderRadius.circular(6),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: SupabaseColors.bg300,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                            color: _copyData
                                ? SupabaseColors.brand.withOpacity(0.4)
                                : SupabaseColors.border,
                          ),
                        ),
                        child: Row(
                          children: [
                            SizedBox(
                              width: 20,
                              height: 20,
                              child: Checkbox(
                                value: _copyData,
                                onChanged: (val) => setState(() => _copyData = val ?? false),
                                activeColor: SupabaseColors.brand,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                                side: const BorderSide(color: SupabaseColors.border),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: const [
                                  Text(
                                    'Copiar dados das tabelas',
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500,
                                      color: SupabaseColors.textPrimary,
                                    ),
                                  ),
                                  SizedBox(height: 2),
                                  Text(
                                    'Incluir todos os registros existentes',
                                    style: TextStyle(fontSize: 11, color: SupabaseColors.textMuted),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
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
                          const Icon(Icons.info_outline_rounded, color: SupabaseColors.info, size: 16),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'O que será duplicado',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: SupabaseColors.textPrimary,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  _copyData
                                      ? '• Estrutura do banco\n• Schemas e tabelas\n• Políticas de segurança\n• Dados das tabelas ✓'
                                      : '• Estrutura do banco\n• Schemas e tabelas\n• Políticas de segurança',
                                  style: const TextStyle(
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
                        _ActionButton(
                          label: 'Duplicar',
                          icon: Icons.copy_rounded,
                          color: SupabaseColors.info,
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

class _ActionButton extends StatefulWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
  });
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onPressed;

  @override
  State<_ActionButton> createState() => _ActionButtonState();
}

class _ActionButtonState extends State<_ActionButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          color: _hover ? widget.color.withOpacity(0.9) : widget.color,
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
                  Icon(widget.icon, size: 16, color: Colors.white),
                  const SizedBox(width: 8),
                  Text(
                    widget.label,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: Colors.white,
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