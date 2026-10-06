import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/project_repository.dart';
import '../providers/project_list_provider.dart';
import '../providers/project_jobs_provider.dart';

class RenameProjectResult {
  const RenameProjectResult({required this.oldRef, required this.newRef});
  final String oldRef;
  final String newRef;
}

class RenameProjectDialog extends ConsumerStatefulWidget {
  const RenameProjectDialog({super.key, required this.projectRef});
  final String projectRef;
  @override
  ConsumerState<RenameProjectDialog> createState() =>
      _RenameProjectDialogState();
}

class _RenameProjectDialogState extends ConsumerState<RenameProjectDialog> {
  bool _submitting = false;
  String? _error;
  String? _newRef;

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final submission = await ref
          .read(projectRepositoryProvider)
          .renameProject(widget.projectRef);
      if (!mounted) return;
      setState(() => _newRef = submission.newRef);
      final result = await ref.read(projectJobsProvider.notifier).waitFor(
            submission.job,
            project: widget.projectRef,
            action: 'rename',
          );
      if (!mounted) return;
      if (!result.ok) {
        throw StateError(result.message ?? 'A rotacao da URL falhou');
      }
      await ref.read(projectListProvider.notifier).refresh(throwOnError: true);
      if (!mounted) return;
      Navigator.of(context).pop(RenameProjectResult(
          oldRef: widget.projectRef, newRef: submission.newRef));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Gerar nova URL do projeto'),
        content: SizedBox(
            width: 480,
            child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                      'O servidor gera uma nova referencia aleatoria. A URL antiga deixa de funcionar, sem redirecionamento.'),
                  const SizedBox(height: 12),
                  const Text(
                      'Banco, dados, chaves e nome do projeto permanecem iguais. Auth e gateway podem ficar indisponiveis durante a troca.'),
                  const SizedBox(height: 16),
                  SelectableText('URL atual: /${widget.projectRef}'),
                  if (_newRef != null) SelectableText('Nova URL: /$_newRef'),
                  if (_error != null)
                    Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(_error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error))),
                ])),
        actions: [
          TextButton(
              onPressed: _submitting ? null : () => Navigator.pop(context),
              child: const Text('Fechar')),
          FilledButton(
              onPressed: _submitting || _newRef != null ? null : _submit,
              child:
                  Text(_submitting ? 'Atualizando URL...' : 'Gerar nova URL')),
        ],
      );
}
