import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/project_repository.dart';
import '../models/job.dart';
import '../providers/favorites_provider.dart';
import '../providers/project_list_provider.dart';
import '../providers/project_jobs_provider.dart';
import '../supabase_colors.dart';

class RenameProjectResult {
  const RenameProjectResult({required this.oldName, required this.newName});
  final String oldName;
  final String newName;
}

class RenameProjectDialog extends ConsumerStatefulWidget {
  const RenameProjectDialog({
    super.key,
    required this.projectName,
    this.currentDisplayName,
  });

  final String projectName;
  final String? currentDisplayName;

  @override
  ConsumerState<RenameProjectDialog> createState() =>
      _RenameProjectDialogState();
}

class _RenameProjectDialogState extends ConsumerState<RenameProjectDialog> {
  final _newNameController = TextEditingController();
  final _displayNameController = TextEditingController();
  bool _submitting = false;
  String? _error;
  String? _validationError;
  Job? _createdJob;

  @override
  void initState() {
    super.initState();
    _displayNameController.text = widget.currentDisplayName ?? '';
  }

  @override
  void dispose() {
    _newNameController.dispose();
    _displayNameController.dispose();
    super.dispose();
  }

  bool _isValidName(String name) {
    return RegExp(r'^[a-z_][a-z0-9_]{2,39}$').hasMatch(name);
  }

  String? _validate() {
    final newName = _newNameController.text.trim();
    if (newName.isEmpty) {
      return 'Informe o novo slug do projeto';
    }
    if (newName == widget.projectName) {
      return 'O novo nome precisa ser diferente do atual';
    }
    if (!_isValidName(newName)) {
      return 'Use letras minúsculas, dígitos ou _ (3–40 chars, começando com letra/_)';
    }
    return null;
  }

  Future<void> _submit() async {
    final err = _validate();
    if (err != null) {
      setState(() => _validationError = err);
      return;
    }
    final newName = _newNameController.text.trim();
    final displayName = _displayNameController.text.trim();

    setState(() {
      _submitting = true;
      _error = null;
      _validationError = null;
    });

    try {
      final job = await ref.read(projectRepositoryProvider).renameProject(
            widget.projectName,
            newName: newName,
            displayName: displayName.isEmpty ? null : displayName,
          );
      if (!mounted) return;
      setState(() => _createdJob = job);

      final result = await ref.read(projectJobsProvider.notifier).waitFor(
            job,
            project: widget.projectName,
            action: 'rename',
          );
      if (!mounted) return;
      if (!result.ok) {
        setState(() {
          _createdJob = null;
          _error = result.message ?? 'A renomeacao falhou (${result.status})';
        });
        return;
      }

      try {
        await ref
            .read(favoritesProvider.notifier)
            .renameFavorite(widget.projectName, newName);
      } catch (_) {
        // O rename remoto já terminou; uma falha local de preferências não
        // deve fazer a operação aparecer como malsucedida.
        ref.invalidate(favoritesProvider);
      }
      if (!mounted) return;
      await ref.read(projectListProvider.notifier).refresh();
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Projeto renomeado: ${widget.projectName} -> $newName'),
          backgroundColor: SupabaseColors.success,
          duration: const Duration(seconds: 6),
        ),
      );

      Navigator.of(
        context,
      ).pop(RenameProjectResult(oldName: widget.projectName, newName: newName));
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().replaceFirst('Exception: ', '');
        });
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final validationError = _validationError;
    final apiError = _error;

    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 520),
        decoration: BoxDecoration(
          color: SupabaseColors.bg200,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildHeader(),
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildWarningBanner(),
                  const SizedBox(height: 18),
                  _buildOldNameRow(),
                  const SizedBox(height: 18),
                  _buildNewNameField(validationError),
                  const SizedBox(height: 18),
                  _buildDisplayNameField(),
                  if (apiError != null) ...[
                    const SizedBox(height: 16),
                    _buildErrorRow(apiError),
                  ],
                ],
              ),
            ),
            _buildFooter(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: SupabaseColors.border)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: SupabaseColors.warning.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(
              Icons.drive_file_rename_outline_rounded,
              color: SupabaseColors.warning,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Renomear projeto e path',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: SupabaseColors.textPrimary,
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Migração completa em background',
                  style: TextStyle(
                    fontSize: 12,
                    color: SupabaseColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          InkWell(
            onTap: _submitting ? null : () => Navigator.pop(context),
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(
                Icons.close_rounded,
                size: 18,
                color: SupabaseColors.textMuted,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWarningBanner() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.warning.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: SupabaseColors.warning.withValues(alpha: 0.4),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.warning_amber_rounded,
            color: SupabaseColors.warning,
            size: 18,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'O projeto ficará offline durante a migração. Containers, '
              'banco de dados, replication slots, tenant Supavisor e o '
              'diretório físico serão renomeados.',
              style: TextStyle(
                fontSize: 12,
                color: SupabaseColors.textSecondary,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOldNameRow() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'NOME ATUAL',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1,
            color: SupabaseColors.textMuted,
          ),
        ),
        const SizedBox(height: 6),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: SupabaseColors.bg300,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: SupabaseColors.border),
          ),
          child: Row(
            children: [
              const Icon(
                Icons.link_rounded,
                size: 14,
                color: SupabaseColors.textMuted,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  widget.projectName,
                  style: const TextStyle(
                    fontSize: 13,
                    fontFamily: 'monospace',
                    color: SupabaseColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildNewNameField(String? validationError) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'NOVO SLUG / PATH',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1,
            color: SupabaseColors.textMuted,
          ),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: _newNameController,
          enabled: !_submitting,
          autocorrect: false,
          enableSuggestions: false,
          style: const TextStyle(
            fontSize: 13,
            fontFamily: 'monospace',
            color: SupabaseColors.textPrimary,
          ),
          decoration: InputDecoration(
            hintText: 'novo_slug_aqui',
            isDense: true,
            errorText: validationError,
            prefixIcon: const Icon(
              Icons.edit_rounded,
              size: 16,
              color: SupabaseColors.textMuted,
            ),
          ),
          onChanged: (_) {
            if (_validationError != null) {
              setState(() => _validationError = null);
            }
          },
        ),
      ],
    );
  }

  Widget _buildDisplayNameField() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'NOME DE EXIBIÇÃO (OPCIONAL)',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1,
            color: SupabaseColors.textMuted,
          ),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: _displayNameController,
          enabled: !_submitting,
          style: const TextStyle(
            fontSize: 13,
            color: SupabaseColors.textPrimary,
          ),
          decoration: const InputDecoration(
            hintText: 'Nome humano do projeto',
            isDense: true,
            prefixIcon: Icon(
              Icons.label_outline_rounded,
              size: 16,
              color: SupabaseColors.textMuted,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildErrorRow(String message) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: SupabaseColors.error.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.error.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.error_outline_rounded,
            color: SupabaseColors.error,
            size: 16,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(fontSize: 12, color: SupabaseColors.error),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFooter() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: SupabaseColors.border)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          TextButton(
            onPressed: _submitting ? null : () => Navigator.pop(context),
            style: TextButton.styleFrom(
              foregroundColor: SupabaseColors.textSecondary,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
            child: const Text('Cancelar', style: TextStyle(fontSize: 13)),
          ),
          const SizedBox(width: 8),
          _submitButton(),
        ],
      ),
    );
  }

  Widget _submitButton() {
    final disabled = _submitting || _createdJob != null;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: BoxDecoration(
        color: disabled ? SupabaseColors.surface300 : SupabaseColors.warning,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: disabled ? null : _submit,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_submitting)
                  const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                else
                  const Icon(
                    Icons.drive_file_rename_outline_rounded,
                    size: 16,
                    color: Colors.white,
                  ),
                const SizedBox(width: 8),
                Text(
                  _submitting
                      ? (_createdJob == null ? 'Iniciando...' : 'Renomeando...')
                      : 'Renomear',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: disabled ? SupabaseColors.textMuted : Colors.white,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
