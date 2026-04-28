import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../supabase_colors.dart';
import '../../data/project_repository.dart';
import '../../providers/project_settings_provider.dart';
import '../../services/projectService.dart';
import '../section_widget.dart';

class _SettingMeta {
  final String key;
  final String label;
  final String description;
  final _FieldType type;
  final String category;

  const _SettingMeta({
    required this.key,
    required this.label,
    required this.description,
    required this.type,
    required this.category,
  });
}

enum _FieldType { toggle, number, text }

const _kIntegerRanges = {
  'JWT_EXPIRY': (min: 60, max: 3153600000),
  'GOTRUE_MAILER_OTP_EXP': (min: 60, max: 3153600000),
  'GOTRUE_PASSWORD_MIN_LENGTH': (min: 6, max: 128),
  'PGRST_DB_MAX_ROWS': (min: 1, max: 1000000000),
  'PGRST_DB_POOL': (min: 1, max: 10000),
  'PGRST_DB_POOL_TIMEOUT': (min: 1, max: 3153600000),
  'PGRST_DB_POOL_ACQUISITION_TIMEOUT': (min: 1, max: 3153600000),
  'FILE_SIZE_LIMIT': (min: 1, max: 9007199254740991),
};

const _kBooleanKeys = {
  'DISABLE_SIGNUP',
  'ENABLE_EMAIL_SIGNUP',
  'ENABLE_EMAIL_AUTOCONFIRM',
  'ENABLE_ANONYMOUS_USERS',
  'ENABLE_PHONE_SIGNUP',
  'ENABLE_PHONE_AUTOCONFIRM',
  'GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED',
  'ENABLE_IMAGE_TRANSFORMATION',
};

const _kSettings = [
  _SettingMeta(
    key: 'DISABLE_SIGNUP',
    label: 'Bloquear Novos Cadastros',
    description:
        'Impede novos cadastros no projeto, mesmo com provedores habilitados',
    type: _FieldType.toggle,
    category: 'Autenticação',
  ),
  _SettingMeta(
    key: 'ENABLE_EMAIL_SIGNUP',
    label: 'Cadastro por E-mail',
    description: 'Permitir que usuários se cadastrem via e-mail',
    type: _FieldType.toggle,
    category: 'Autenticação',
  ),
  _SettingMeta(
    key: 'ENABLE_EMAIL_AUTOCONFIRM',
    label: 'Auto-confirmar E-mail',
    description: 'Confirmar e-mail automaticamente ao cadastrar',
    type: _FieldType.toggle,
    category: 'Autenticação',
  ),
  _SettingMeta(
    key: 'ENABLE_ANONYMOUS_USERS',
    label: 'Usuários Anônimos',
    description: 'Permitir autenticação anônima',
    type: _FieldType.toggle,
    category: 'Autenticação',
  ),
  _SettingMeta(
    key: 'ENABLE_PHONE_SIGNUP',
    label: 'Cadastro por Telefone',
    description: 'Permitir cadastro via número de telefone',
    type: _FieldType.toggle,
    category: 'Autenticação',
  ),
  _SettingMeta(
    key: 'ENABLE_PHONE_AUTOCONFIRM',
    label: 'Auto-confirmar Telefone',
    description: 'Confirmar telefone automaticamente ao cadastrar',
    type: _FieldType.toggle,
    category: 'Autenticação',
  ),
  _SettingMeta(
    key: 'JWT_EXPIRY',
    label: 'Expiração do JWT (seg)',
    description: 'Tempo em segundos até o token JWT expirar',
    type: _FieldType.number,
    category: 'Tokens e Segurança',
  ),
  _SettingMeta(
    key: 'GOTRUE_MAILER_OTP_EXP',
    label: 'Expiração OTP E-mail (seg)',
    description: 'Tempo em segundos até o link/código de e-mail expirar',
    type: _FieldType.number,
    category: 'Tokens e Segurança',
  ),
  _SettingMeta(
    key: 'GOTRUE_PASSWORD_MIN_LENGTH',
    label: 'Tamanho mín. da senha',
    description: 'Número mínimo de caracteres para senhas',
    type: _FieldType.number,
    category: 'Tokens e Segurança',
  ),
  _SettingMeta(
    key: 'GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED',
    label: 'Implicit Flow Externo',
    description: 'Habilitar OAuth implicit flow para provedores externos',
    type: _FieldType.toggle,
    category: 'Tokens e Segurança',
  ),
  _SettingMeta(
    key: 'PGRST_DB_SCHEMAS',
    label: 'Schemas Expostos (PostgREST)',
    description: 'Schemas acessíveis via API REST (separados por vírgula)',
    type: _FieldType.text,
    category: 'Banco de Dados',
  ),
  _SettingMeta(
    key: 'PGRST_DB_MAX_ROWS',
    label: 'Máx. de Linhas por Consulta',
    description: 'Limite padrão de linhas retornadas pela API REST',
    type: _FieldType.number,
    category: 'Banco de Dados',
  ),
  _SettingMeta(
    key: 'PGRST_DB_POOL',
    label: 'Pool do PostgREST',
    description: 'Quantidade de conexões que a API REST pode manter abertas',
    type: _FieldType.number,
    category: 'Banco de Dados',
  ),
  _SettingMeta(
    key: 'PGRST_DB_POOL_TIMEOUT',
    label: 'Timeout do Pool (seg)',
    description: 'Tempo de espera por conexão livre no pool do PostgREST',
    type: _FieldType.number,
    category: 'Banco de Dados',
  ),
  _SettingMeta(
    key: 'PGRST_DB_POOL_ACQUISITION_TIMEOUT',
    label: 'Timeout de Aquisição (seg)',
    description: 'Tempo máximo para a API REST adquirir uma conexão do pool',
    type: _FieldType.number,
    category: 'Banco de Dados',
  ),
  _SettingMeta(
    key: 'FILE_SIZE_LIMIT',
    label: 'Limite de Arquivo (bytes)',
    description: 'Tamanho máximo de upload em bytes',
    type: _FieldType.number,
    category: 'Storage',
  ),
  _SettingMeta(
    key: 'ENABLE_IMAGE_TRANSFORMATION',
    label: 'Transformação de Imagens',
    description: 'Habilitar resize/otimização de imagens via Storage',
    type: _FieldType.toggle,
    category: 'Storage',
  ),
];

class EnvSettingsSection extends ConsumerStatefulWidget {
  const EnvSettingsSection({
    super.key,
    required this.projectRef,
    required this.isAdmin,
  });

  final String projectRef;
  final bool isAdmin;

  @override
  ConsumerState<EnvSettingsSection> createState() => _EnvSettingsSectionState();
}

class _EnvSettingsSectionState extends ConsumerState<EnvSettingsSection> {
  Map<String, String> _original = {};
  Map<String, String> _current = {};
  bool _saving = false;
  bool _recreating = false;
  List<String> _affectedServices = [];

  bool get _hasChanges {
    if (_original.length != _current.length) return true;
    for (final key in _current.keys) {
      if (_original[key] != _current[key]) return true;
    }
    return false;
  }

  Map<String, String> get _validationErrors {
    final errors = <String, String>{};
    for (final meta in _kSettings) {
      final error = _validateSetting(meta.key, _current[meta.key] ?? '');
      if (error != null) {
        errors[meta.key] = error;
      }
    }
    return errors;
  }

  bool get _hasValidationErrors => _validationErrors.isNotEmpty;

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';

    const units = ['KB', 'MB', 'GB', 'TB', 'PB'];
    double size = bytes.toDouble();
    int unitIndex = -1;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    if (unitIndex == 1 && size >= 1000) {
      size /= 1024;
      unitIndex++;
    }

    return '${size.toStringAsFixed(2)} ${units[unitIndex]}';
  }

  void _initFromSettings(Map<String, String> settings) {
    if (_original.isEmpty) {
      _original = Map.from(settings);
      _current = Map.from(settings);
    }
  }

  void _updateValue(String key, String value) {
    setState(() {
      _current[key] = value;
    });
  }

  String _normalizeInputValue(String key, String value) {
    if (key == 'PGRST_DB_SCHEMAS') {
      return value
          .split(',')
          .map((part) => part.trim())
          .where((part) => part.isNotEmpty)
          .join(',');
    }
    return value.trim();
  }

  String? _validateSetting(String key, String value) {
    if (value.contains('\n') ||
        value.contains('\r') ||
        value.contains('\u0000')) {
      return 'Valor não pode conter quebra de linha ou byte nulo.';
    }

    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return 'Valor obrigatório.';
    }

    if (_kBooleanKeys.contains(key)) {
      final normalized = trimmed.toLowerCase();
      if (normalized != 'true' && normalized != 'false') {
        return 'Use true ou false.';
      }
      return null;
    }

    final range = _kIntegerRanges[key];
    if (range != null) {
      final parsed = int.tryParse(trimmed);
      if (parsed == null) {
        return 'Use apenas números inteiros.';
      }
      if (parsed < range.min || parsed > range.max) {
        return 'Use um valor entre ${range.min} e ${range.max}.';
      }
      return null;
    }

    if (key == 'PGRST_DB_SCHEMAS') {
      final schemas = trimmed.split(',').map((part) => part.trim()).toList();
      if (schemas.any((part) => part.isEmpty)) {
        return 'Informe schemas separados por vírgula.';
      }
      final validIdentifier = RegExp(r'^[a-z_][a-z0-9_]*$');
      for (final schema in schemas) {
        if (!validIdentifier.hasMatch(schema)) {
          return 'Schema inválido: $schema.';
        }
      }
    }

    return null;
  }

  bool _isTrue(String? value) {
    if (value == null) return false;
    final v = value.trim().toLowerCase();
    return v == 'true' || v == '1' || v == 'yes';
  }

  Future<void> _save() async {
    final validationErrors = _validationErrors;
    if (validationErrors.isNotEmpty) {
      final firstError = validationErrors.values.first;
      _showSnack('Corrija as configurações: $firstError', SupabaseColors.error);
      setState(() {});
      return;
    }

    final changes = <String, String>{};
    for (final key in _current.keys) {
      if (_original[key] != _current[key]) {
        changes[key] = _normalizeInputValue(key, _current[key]!);
      }
    }
    if (changes.isEmpty) return;

    setState(() => _saving = true);
    try {
      final affected = await ref
          .read(projectRepositoryProvider)
          .updateProjectSettings(widget.projectRef, changes);

      setState(() {
        _original = Map.from(_current);
        _affectedServices = affected;
      });

      _showSnack('Configurações salvas!', SupabaseColors.success);
    } catch (e) {
      final msg = e.toString().replaceFirst('Exception: ', '');
      _showSnack('Erro ao salvar: $msg', SupabaseColors.error);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _confirmAndRecreate() async {
    if (_affectedServices.isEmpty) return;

    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: SupabaseColors.bg200,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: SupabaseColors.border),
        ),
        title: const Row(
          children: [
            Icon(Icons.restart_alt_rounded, color: SupabaseColors.warning),
            SizedBox(width: 8),
            Text(
              'Recriar serviços?',
              style: TextStyle(color: SupabaseColors.textPrimary),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Os seguintes serviços serão parados e recriados para aplicar as novas configurações:',
              style: TextStyle(
                color: SupabaseColors.textSecondary,
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: _affectedServices
                  .map(
                    (svc) => Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: SupabaseColors.warning.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(
                          color: SupabaseColors.warning.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Text(
                        svc,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          fontFamily: 'monospace',
                          color: SupabaseColors.warning,
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 12),
            const Text(
              'O projeto ficará temporariamente indisponível durante o processo.',
              style: TextStyle(color: SupabaseColors.textMuted, fontSize: 11),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(
              foregroundColor: SupabaseColors.warning,
            ),
            child: const Text('Recriar'),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    setState(() => _recreating = true);
    try {
      final result = await ref
          .read(projectRepositoryProvider)
          .recreateServices(widget.projectRef, _affectedServices);

      final job = result.job;
      if (job != null) {
        final waited = await ProjectService.waitForJob(job.id);
        _showSnack(
          waited.message ??
              (waited.ok
                  ? 'Serviços recriados: ${_affectedServices.join(", ")}'
                  : 'Falha ao recriar serviços'),
          waited.ok ? SupabaseColors.success : SupabaseColors.error,
        );
        if (!waited.ok) return;
      } else {
        _showSnack(
          result.message ??
              'Serviços recriados: ${_affectedServices.join(", ")}',
          SupabaseColors.success,
        );
      }

      setState(() => _affectedServices = []);
    } catch (e) {
      final msg = e.toString().replaceFirst('Exception: ', '');
      _showSnack('Erro ao recriar: $msg', SupabaseColors.error);
    } finally {
      if (mounted) setState(() => _recreating = false);
    }
  }

  void _showSnack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(color: Colors.white)),
        backgroundColor: color,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        margin: const EdgeInsets.all(16),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final settingsAsync = ref.watch(
      projectEnvSettingsProvider(widget.projectRef),
    );

    return settingsAsync.when(
      loading: () => _buildLoading(),
      error: (err, _) => _buildError(err.toString()),
      data: (settings) {
        _initFromSettings(settings);
        return _buildContent();
      },
    );
  }

  Widget _buildLoading() {
    return SectionWidget(
      title: 'CONFIGURAÇÕES DO AMBIENTE',
      child: const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: SupabaseColors.brand,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildError(String error) {
    final clean = error.replaceFirst('Exception: ', '');
    return SectionWidget(
      title: 'CONFIGURAÇÕES DO AMBIENTE',
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Row(
          children: [
            const Icon(
              Icons.error_outline,
              size: 16,
              color: SupabaseColors.error,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                clean,
                style: const TextStyle(
                  fontSize: 12,
                  color: SupabaseColors.error,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    final categories = <String, List<_SettingMeta>>{};
    for (final meta in _kSettings) {
      categories.putIfAbsent(meta.category, () => []);
      categories[meta.category]!.add(meta);
    }

    final categoryIcons = {
      'Autenticação': Icons.verified_user_rounded,
      'Tokens e Segurança': Icons.security_rounded,
      'Banco de Dados': Icons.storage_rounded,
      'Storage': Icons.cloud_upload_rounded,
    };

    return SectionWidget(
      title: 'CONFIGURAÇÕES DO AMBIENTE',
      trailing: widget.isAdmin && _hasChanges
          ? _saving
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: SupabaseColors.brand,
                  ),
                )
              : Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: _hasValidationErrors ? null : _save,
                    borderRadius: BorderRadius.circular(6),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: SupabaseColors.brand.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: (_hasValidationErrors
                                  ? SupabaseColors.error
                                  : SupabaseColors.brand)
                              .withValues(alpha: 0.3),
                        ),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.save_rounded,
                            size: 14,
                            color: SupabaseColors.brand,
                          ),
                          SizedBox(width: 6),
                          Text(
                            'Salvar',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: SupabaseColors.brand,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                )
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_affectedServices.isNotEmpty) ...[
            _buildRestartBanner(),
            const SizedBox(height: 16),
          ],
          if (!widget.isAdmin) ...[
            _buildReadOnlyBanner(),
            const SizedBox(height: 16),
          ],
          ...categories.entries.map((entry) {
            final icon = categoryIcons[entry.key] ?? Icons.settings;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildCategoryHeader(entry.key, icon),
                const SizedBox(height: 8),
                ...entry.value.map((meta) => _buildSettingRow(meta)),
                const SizedBox(height: 16),
              ],
            );
          }),
        ],
      ),
    );
  }

  Widget _buildRestartBanner() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.warning.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: SupabaseColors.warning.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.restart_alt_rounded,
                size: 18,
                color: SupabaseColors.warning,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Serviços precisam ser recriados',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: SupabaseColors.warning,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Afetados: ${_affectedServices.join(", ")}',
                      style: const TextStyle(
                        fontSize: 11,
                        fontFamily: 'monospace',
                        color: SupabaseColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              _recreating
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: SupabaseColors.warning,
                      ),
                    )
                  : Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: _confirmAndRecreate,
                        borderRadius: BorderRadius.circular(6),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: SupabaseColors.warning.withValues(
                              alpha: 0.15,
                            ),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: SupabaseColors.warning.withValues(
                                alpha: 0.4,
                              ),
                            ),
                          ),
                          child: const Text(
                            'Aplicar',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: SupabaseColors.warning,
                            ),
                          ),
                        ),
                      ),
                    ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildReadOnlyBanner() {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: SupabaseColors.info.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.info.withValues(alpha: 0.2)),
      ),
      child: const Row(
        children: [
          Icon(Icons.info_outline, size: 14, color: SupabaseColors.info),
          SizedBox(width: 8),
          Text(
            'Somente administradores podem editar estas configurações.',
            style: TextStyle(fontSize: 11, color: SupabaseColors.textMuted),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryHeader(String label, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 14, color: SupabaseColors.textMuted),
        const SizedBox(width: 8),
        Text(
          label.toUpperCase(),
          style: const TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.2,
            color: SupabaseColors.textMuted,
          ),
        ),
      ],
    );
  }

  Widget _buildSettingRow(_SettingMeta meta) {
    final value = _current[meta.key] ?? '';
    final enabled = widget.isAdmin && !_saving;
    final error = _validateSetting(meta.key, value);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: SupabaseColors.bg300,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    meta.label,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: SupabaseColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    meta.description,
                    style: const TextStyle(
                      fontSize: 11,
                      color: SupabaseColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            _buildFieldWidget(meta, value, enabled, error),
          ],
        ),
      ),
    );
  }

  Widget _buildFieldWidget(
    _SettingMeta meta,
    String value,
    bool enabled,
    String? error,
  ) {
    switch (meta.type) {
      case _FieldType.toggle:
        return SizedBox(
          height: 28,
          child: FittedBox(
            fit: BoxFit.contain,
            child: Switch(
              value: _isTrue(value),
              onChanged: enabled
                  ? (v) => _updateValue(meta.key, v ? 'true' : 'false')
                  : null,
              activeThumbColor: SupabaseColors.brand,
              inactiveThumbColor: SupabaseColors.textMuted,
              inactiveTrackColor: SupabaseColors.bg300,
            ),
          ),
        );
      case _FieldType.number:
        final isFileSize = meta.key == 'FILE_SIZE_LIMIT';
        final bytes = int.tryParse(value) ?? 0;
        final formattedSize = _formatBytes(bytes);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 120,
                  height: 32,
                  child: TextField(
                    controller: TextEditingController(text: value)
                      ..selection = TextSelection.collapsed(
                        offset: value.length,
                      ),
                    enabled: enabled,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    onChanged: (v) => _updateValue(meta.key, v),
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textPrimary,
                    ),
                    decoration: _fieldDecoration(error),
                  ),
                ),
                if (isFileSize && bytes > 0) ...[
                  const SizedBox(width: 8),
                  Text(
                    '≈ $formattedSize',
                    style: const TextStyle(
                      fontSize: 11,
                      color: SupabaseColors.textMuted,
                      fontFamily: 'monospace',
                    ),
                  ),
                ],
              ],
            ),
            if (error != null) _buildFieldError(error),
          ],
        );
      case _FieldType.text:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            SizedBox(
              width: 180,
              height: 32,
              child: TextField(
                controller: TextEditingController(text: value)
                  ..selection = TextSelection.collapsed(offset: value.length),
                enabled: enabled,
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[a-z0-9_,]')),
                ],
                onChanged: (v) => _updateValue(meta.key, v),
                style: const TextStyle(
                  fontSize: 12,
                  fontFamily: 'monospace',
                  color: SupabaseColors.textPrimary,
                ),
                decoration: _fieldDecoration(error),
              ),
            ),
            if (error != null) _buildFieldError(error),
          ],
        );
    }
  }

  InputDecoration _fieldDecoration(String? error) {
    final borderColor =
        error == null ? SupabaseColors.border : SupabaseColors.error;
    return InputDecoration(
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      filled: true,
      fillColor: SupabaseColors.bg200,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(4),
        borderSide: BorderSide(color: borderColor),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(4),
        borderSide: BorderSide(color: borderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(4),
        borderSide: BorderSide(
          color: error == null ? SupabaseColors.brand : SupabaseColors.error,
          width: 1.5,
        ),
      ),
    );
  }

  Widget _buildFieldError(String error) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: SizedBox(
        width: 180,
        child: Text(
          error,
          textAlign: TextAlign.right,
          style: const TextStyle(fontSize: 10, color: SupabaseColors.error),
        ),
      ),
    );
  }
}
