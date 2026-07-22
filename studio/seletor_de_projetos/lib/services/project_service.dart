import 'package:flutter/material.dart';

import '../data/api_client.dart';
import '../models/job.dart';

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
    SubmittedJobWaiter? submittedJobWaiter,
  }) async {
    final confirmed = await _showConfirmationDialog(context, projectRef);
    if (!confirmed || !context.mounted) return false;

    final password = await _showPasswordDialog(context);
    if (password == null || password.isEmpty || !context.mounted) return false;

    return await _executeProjectDeletion(
      context,
      projectRef,
      password,
      submittedJobWaiter: submittedJobWaiter,
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

  static Future<String?> _showPasswordDialog(BuildContext context) async {
    final passwordController = TextEditingController();
    final formKey = GlobalKey<FormState>();

    return showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('Senha de Exclusão'),
        content: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Digite a senha para confirmar a operação:'),
              const SizedBox(height: 16),
              TextFormField(
                controller: passwordController,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Senha de Exclusão',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.lock),
                ),
                validator: (value) =>
                    value == null || value.isEmpty ? 'Senha obrigatória' : null,
                autofocus: true,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () {
              if (formKey.currentState!.validate()) {
                Navigator.pop(context, passwordController.text);
              }
            },
            child: const Text('Confirmar'),
          ),
        ],
      ),
    );
  }

  static Future<bool> _executeProjectDeletion(
    BuildContext context,
    String projectRef,
    String password, {
    SubmittedJobWaiter? submittedJobWaiter,
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
      final response = await (() async {
        final client = ApiClient();
        try {
          return await client.delete(
            Uri.parse('/api/admin/projects/$projectRef'),
            headers: {
              'X-Delete-Password': password,
              'Content-Type': 'application/json',
            },
          );
        } finally {
          client.close();
        }
      })();

      if (response.statusCode != 202) {
        throw ApiException.fromResponse(response);
      }

      final job = Job.fromResponse(response);
      final waited = submittedJobWaiter == null
          ? await waitForJob(job.id)
          : await submittedJobWaiter(job);
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

  static Future<JobWaitResult> waitForJob(
    String jobId, {
    Duration every = const Duration(seconds: 3),
    int max = 100,
    void Function(Map<String, dynamic> data)? onUpdate,
    RequestCancellation? cancellation,
  }) async {
    Map<String, dynamic> lastData = const {};
    final client = ApiClient();
    try {
      for (var i = 0; i < max; i++) {
        if (cancellation?.isCancelled == true) {
          throw const ApiException(
            ApiFailureKind.cancelled,
            'Acompanhamento do job cancelado',
          );
        }
        if (i > 0) await Future.delayed(every);
        final response = await client.get(
          Uri.parse('/api/projects/status/$jobId'),
          cancellation: cancellation,
        );
        if (response.statusCode != 200) {
          throw ApiException.fromResponse(response);
        }
        final data = decodeJsonObject(
          response,
          context: 'Acompanhamento do job',
        );
        onUpdate?.call(data);

        final status = data['status']?.toString();
        if (status == null || status.isEmpty) {
          throw const ApiException(
            ApiFailureKind.invalidResponse,
            'Resposta de job sem status',
          );
        }
        final message = data['message']?.toString();
        final action = data['action']?.toString();
        final progress = (data['progress'] as num?)?.toInt();
        final currentStep = data['current_step']?.toString();
        lastData = data;

        if (status == 'done') {
          return JobWaitResult(
            ok: true,
            status: status,
            message: message,
            action: action,
            progress: progress,
            currentStep: currentStep,
          );
        }
        if (status == 'failed' || status == 'cancelled') {
          final diagnostic = [
            if (message != null && message.isNotEmpty) message,
            if (currentStep != null) 'Etapa: $currentStep (${progress ?? 0}%)',
          ].join('\n');
          return JobWaitResult(
            ok: false,
            status: status,
            message: diagnostic.isEmpty ? null : diagnostic,
            action: action,
            progress: progress,
            currentStep: currentStep,
          );
        }
      }
    } finally {
      client.close();
    }
    return JobWaitResult(
      ok: false,
      status: 'timeout',
      message:
          'Tempo limite excedido em ${lastData['current_step'] ?? 'etapa desconhecida'} '
          '(${lastData['progress'] ?? 0}%).',
      action: lastData['action']?.toString(),
      progress: (lastData['progress'] as num?)?.toInt(),
      currentStep: lastData['current_step']?.toString(),
    );
  }

  static Future<bool> waitUntilReady(
    String jobId, {
    Duration every = const Duration(seconds: 3),
    int max = 100,
  }) async {
    final result = await waitForJob(jobId, every: every, max: max);
    return result.ok;
  }
}
