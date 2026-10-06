import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../supabase_colors.dart';
import '../../data/project_repository.dart';
import '../../providers/project_settings_provider.dart';
import '../../providers/project_jobs_provider.dart';
import '../section_widget.dart';
import 'env_setting_field.dart';
import 'env_settings_metadata.dart';

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
    for (final meta in kEnvSettings) {
      final error = _validateSetting(meta.key, _current[meta.key] ?? '');
      if (error != null) {
        errors[meta.key] = error;
      }
    }
    return errors;
  }

  bool get _hasValidationErrors => _validationErrors.isNotEmpty;

  void _initFromSettings(ProjectSettingsData data) {
    if (_original.isEmpty) {
      _original = Map.from(data.settings);
      _current = Map.from(data.settings);
      _affectedServices = List.from(data.pendingAffectedServices);
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
    if (key == 'PROJECT_MEM_LIMIT') return value.trim().toLowerCase();
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

    if (kEnvBooleanKeys.contains(key)) {
      final normalized = trimmed.toLowerCase();
      if (normalized != 'true' && normalized != 'false') {
        return 'Use true ou false.';
      }
      return null;
    }

    final range = kEnvIntegerRanges[key];
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

    if (key == 'PROJECT_MEM_LIMIT') {
      if (!RegExp(r'^\d+[mg]$').hasMatch(trimmed.toLowerCase())) {
        return 'Use o formato 256m ou 1g.';
      }
      return null;
    }
    if (key == 'PROJECT_CPUS') {
      if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(trimmed)) {
        return 'Use o formato 1.50 (máx. 2 casas).';
      }
      return null;
    }
    if (key == 'PROJECT_PIDS_LIMIT') {
      final parsed = int.tryParse(trimmed);
      if (parsed == null || parsed < 1) {
        return 'Use um número inteiro maior que zero.';
      }
      return null;
    }

    return null;
  }

  Future<void> _save() async {
    if (ref.read(activeProjectJobProvider(widget.projectRef)) != null) {
      _showSnack(
        'Aguarde a operação atual do projeto terminar.',
        SupabaseColors.warning,
      );
      return;
    }
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
      final result = await ref
          .read(projectRepositoryProvider)
          .updateProjectSettings(widget.projectRef, changes);

      if (!mounted) return;
      setState(() {
        _original = Map.from(_current);
        _affectedServices = result.affectedServices;
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
    if (ref.read(activeProjectJobProvider(widget.projectRef)) != null) {
      _showSnack(
        'Aguarde a operação atual do projeto terminar.',
        SupabaseColors.warning,
      );
      return;
    }

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

    if (confirm != true || !mounted) return;

    setState(() => _recreating = true);
    try {
      final result = await ref
          .read(projectRepositoryProvider)
          .recreateServices(widget.projectRef, _affectedServices);

      final job = result.job;
      if (job != null) {
        final waited = await ref.read(projectJobsProvider.notifier).waitFor(
              job,
              project: widget.projectRef,
              action: 'recreate_services',
            );
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

      if (!mounted) return;
      setState(() {
        _affectedServices = [];
      });
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
    final activeJob = ref.watch(activeProjectJobProvider(widget.projectRef));

    return settingsAsync.when(
      loading: () => _buildLoading(),
      error: (err, _) => _buildError(err.toString()),
      data: (settings) {
        _initFromSettings(settings);
        return _buildContent(activeJob != null);
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

  Widget _buildContent(bool projectBusy) {
    final categories = <String, List<SettingMeta>>{};
    for (final meta in kEnvSettings) {
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
          ? _saving || projectBusy
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
                    onTap: _hasValidationErrors || projectBusy ? null : _save,
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
                ...entry.value.map(
                  (meta) => _buildSettingRow(meta, projectBusy),
                ),
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

  Widget _buildSettingRow(SettingMeta meta, bool projectBusy) {
    final value = _current[meta.key] ?? '';
    final enabled = widget.isAdmin && !_saving && !projectBusy;
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
            EnvSettingField(
              meta: meta,
              value: value,
              onChanged: (v) => _updateValue(meta.key, v),
              enabled: enabled,
              error: error,
            ),
          ],
        ),
      ),
    );
  }
}
