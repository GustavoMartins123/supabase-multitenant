import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../data/api_client.dart';
import '../models/job.dart';
import 'step_up_authentication_service.dart';
import '../widgets/step_up_authentication_dialog.dart';

class JobWaitResult {
  const JobWaitResult({
    required this.ok,
    required this.status,
    this.message,
    this.action,
    this.progress,
    this.currentStep,
  });

  final bool ok;
  final String status;
  final String? message;
  final String? action;
  final int? progress;
  final String? currentStep;
}

typedef SubmittedJobWaiter = Future<JobWaitResult> Function(Job job);

class ProjectService {
  static Future<bool> confirmAndDeleteProject(
    BuildContext context,
    String projectRef, {
    required StepUpTokenRequester requestStepUpToken,
    required SubmittedJobWaiter submittedJobWaiter,
    ApiClient? apiClient,
  }) async {
    final confirmed = await _showConfirmationDialog(context, projectRef);
    if (!confirmed || !context.mounted) return false;

    final stepUpToken = await showStepUpAuthenticationDialog(
      context,
      title: 'Reautenticar para excluir',
      description:
          'Confirme sua identidade antes de excluir permanentemente este projeto.',
      authenticate: (password) => requestStepUpToken(
        password: password,
        action: StepUpAction.deleteProject,
        projectRef: projectRef,
        resourceId: projectRef,
      ),
    );
    if (stepUpToken == null || !context.mounted) return false;

    return await _executeProjectDeletion(
      context,
      projectRef,
      stepUpToken,
      submittedJobWaiter: submittedJobWaiter,
      apiClient: apiClient,
    );
  }

  static Future<bool> _showConfirmationDialog(
    BuildContext context,
    String projectRef,
  ) async {
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('⚠️ ATENÇÃO - EXCLUSÃO PERMANENTE'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Você está prestes a EXCLUIR PERMANENTEMENTE o projeto "$projectRef".',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            const Text('Esta ação irá:'),
            const Text('• Parar e remover todos os containers Docker'),
            const Text('• Excluir todos os arquivos do projeto'),
            const Text('• Apagar o banco de dados completamente'),
            const Text('• Remover todos os registros do sistema'),
            const SizedBox(height: 16),
            const Text(
              '⚠️ ESTA AÇÃO NÃO PODE SER DESFEITA!',
              style: TextStyle(color: Colors.red, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Confirmar Exclusão'),
          ),
        ],
      ),
    ).then((value) => value ?? false);
  }

  static Future<bool> _executeProjectDeletion(
    BuildContext context,
    String projectRef,
    String stepUpToken, {
    required SubmittedJobWaiter submittedJobWaiter,
    ApiClient? apiClient,
  }) async {
    var loadingDialogOpen = true;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const AlertDialog(
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Excluindo projeto...'),
            Text('Esta operação pode levar alguns minutos.'),
          ],
        ),
      ),
    );

    try {
      late final http.Response response;
      final client = apiClient ?? ApiClient();
      try {
        response = await client.delete(
          Uri.parse('/api/admin/projects/$projectRef'),
          headers: {
            'X-Step-Up-Token': stepUpToken,
            'Content-Type': 'application/json',
          },
        );
      } finally {
        stepUpToken = '';
        if (apiClient == null) client.close();
      }

      if (response.statusCode != 202) {
        throw ApiException.fromResponse(response);
      }

      final job = Job.fromResponse(response);
      final waited = await submittedJobWaiter(job);
      if (!context.mounted) return waited.ok;
      Navigator.pop(context);
      loadingDialogOpen = false;

      await _showDeleteResultDialog(
        context,
        message: waited.message ??
            (waited.ok
                ? 'Projeto excluído com sucesso.'
                : 'Falha ao excluir projeto.'),
        success: waited.ok,
      );
      return waited.ok;
    } catch (e) {
      if (!context.mounted) return false;
      if (loadingDialogOpen) Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Erro na exclusão: $e'),
          backgroundColor: Colors.red,
        ),
      );
      return false;
    }
  }

  static Future<void> _showDeleteResultDialog(
    BuildContext context, {
    required String message,
    required bool success,
  }) async {
    final isWarning = success && message.toLowerCase().contains('aviso');
    final icon = success
        ? (isWarning ? Icons.warning : Icons.check_circle)
        : Icons.error;
    final color =
        success ? (isWarning ? Colors.orange : Colors.green) : Colors.red;

    await showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Icon(icon, color: color, size: 48),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message, style: const TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

}
