import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class ProjectService {
  static Future<bool> confirmAndDeleteProject(BuildContext context, String projectRef) async {
    final confirmed = await _showConfirmationDialog(context, projectRef);
    if (!confirmed) return false;

    final password = await _showPasswordDialog(context);
    if (password == null || password.isEmpty) return false;

    return await _executeProjectDeletion(context, projectRef, password);
  }

  static Future<bool> _showConfirmationDialog(BuildContext context, String projectRef) async {
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
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
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
                validator: (value) => value == null || value.isEmpty ? 'Senha obrigatória' : null,
                autofocus: true,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancelar')),
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

  static Future<bool> _executeProjectDeletion(BuildContext context, String projectRef, String password) async {
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

      Navigator.pop(context); // Fecha o diálogo de loading

      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        await showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: Icon(
              result['status'] == 'success' ? Icons.check_circle : Icons.warning,
              color: result['status'] == 'success' ? Colors.green : Colors.orange,
              size: 48,
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(result['message'] ?? 'Projeto excluído', style: const TextStyle(fontWeight: FontWeight.bold)),
                if (result['errors'] != null && result['errors'].isNotEmpty) ...[
                  const SizedBox(height: 16),
                  const Text('Erros encontrados:'),
                  ...result['errors'].map<Widget>((e) => Text('• $e')),
                ],
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
        return true;
      } else {
        throw Exception(jsonDecode(response.body)['detail'] ?? response.body);
      }
    } catch (e) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erro na exclusão: $e'), backgroundColor: Colors.red),
      );
      return false;
    }
  }

  static Future<bool> waitUntilReady(String jobId,
      {Duration every = const Duration(seconds: 3), int max = 100}) async {
    for (var i = 0; i < max; i++) {
      await Future.delayed(every);
      final st = await http
          .get(Uri.parse('/api/projects/status/$jobId'))
          .then((r) => jsonDecode(r.body)['status'])
          .catchError((_) => null);
      if (st == 'done') return true;
      if (st == 'failed') return false;
    }
    return false; // timeout
  }
}
