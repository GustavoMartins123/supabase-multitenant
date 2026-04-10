import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../models/job.dart';

class JobWaitResult {
  const JobWaitResult({required this.ok, required this.status, this.message});

  final bool ok;
  final String status;
  final String? message;
}

class ProjectService {
  static Future<bool> confirmAndDeleteProject(
    BuildContext context,
    String projectRef,
  ) async {
    final confirmed = await _showConfirmationDialog(context, projectRef);
    if (!confirmed) return false;

    final password = await _showPasswordDialog(context);
    if (password == null || password.isEmpty) return false;

    return await _executeProjectDeletion(context, projectRef, password);
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
    String password,
  ) async {
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
      final response = await http.delete(
        Uri.parse('/api/admin/projects/$projectRef'),
        headers: {
          'X-Delete-Password': password,
          'Content-Type': 'application/json',
        },
      );

      final job = Job.fromResponse(response);
      if (job != null) {
        final waited = await waitForJob(job.id);
        if (context.mounted) {
          Navigator.pop(context);
        }

        await _showDeleteResultDialog(
          context,
          message:
              waited.message ??
              (waited.ok
                  ? 'Projeto excluído com sucesso.'
                  : 'Falha ao excluir projeto.'),
          success: waited.ok,
        );
        return waited.ok;
      }

      if (context.mounted) {
        Navigator.pop(context);
      }

      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        final status = result['status']?.toString() ?? 'unknown';
        final errors = (result['errors'] as List?)?.map((e) => e.toString());
        final message = [
          result['message']?.toString() ?? 'Projeto excluído',
          if (errors != null && errors.isNotEmpty) errors.join('\n'),
        ].where((part) => part.isNotEmpty).join('\n');

        await _showDeleteResultDialog(
          context,
          message: message,
          success: status == 'success',
        );
        return status == 'success';
      } else {
        throw Exception(jsonDecode(response.body)['detail'] ?? response.body);
      }
    } catch (e) {
      if (context.mounted) {
        Navigator.pop(context);
      }
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
    final color = success
        ? (isWarning ? Colors.orange : Colors.green)
        : Colors.red;

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
  }) async {
    for (var i = 0; i < max; i++) {
      await Future.delayed(every);
      final data = await http
          .get(Uri.parse('/api/projects/status/$jobId'))
          .then((r) => jsonDecode(r.body) as Map<String, dynamic>)
          .catchError((_) => <String, dynamic>{});

      final st = data['status']?.toString() ?? 'unknown';
      final message = data['message']?.toString();

      if (st == 'done') {
        return JobWaitResult(ok: true, status: st, message: message);
      }
      if (st == 'failed') {
        return JobWaitResult(ok: false, status: st, message: message);
      }
    }
    return const JobWaitResult(
      ok: false,
      status: 'timeout',
      message: 'Tempo limite excedido aguardando a operacao.',
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
