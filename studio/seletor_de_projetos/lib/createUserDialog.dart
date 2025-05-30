import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
class CreateUserDialog extends StatefulWidget {
  final VoidCallback onUserCreated;

  const CreateUserDialog({
    super.key,
    required this.onUserCreated,
  });

  @override
  State<CreateUserDialog> createState() => _CreateUserDialogState();
}

class _CreateUserDialogState extends State<CreateUserDialog> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _displayNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  bool _isLoading = false;
  bool _showPassword = false;
  bool _showConfirmPassword = false;

  @override
  void dispose() {
    _usernameController.dispose();
    _displayNameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _createUser() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    try {
      final response = await http.post(
        Uri.parse('/api/admin/users/signup'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': _usernameController.text.trim(),
          'display_name': _displayNameController.text.trim(),
          'email': _emailController.text.trim(),
          'password': _passwordController.text,
        }),
      );

      if (response.statusCode == 201) {
        Navigator.of(context).pop();
        widget.onUserCreated();
      } else {
        final error = jsonDecode(response.body)['error'] ?? 'Erro desconhecido';
        _showError(error);
      }
    } catch (e) {
      _showError('Erro ao criar usuário: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  void _showError(String message) {
    _showSnackBar(message, Colors.red);
  }

  void _showSnackBar(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      child: Container(
        width: 500,
        padding: const EdgeInsets.all(24),
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const Icon(Icons.person_add, size: 28),
                  const SizedBox(width: 12),
                  Text(
                    'Novo Usuário',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 24),

              // Username
              TextFormField(
                controller: _usernameController,
                decoration: const InputDecoration(
                  labelText: 'Nome de usuário *',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.account_circle),
                  helperText: 'Mínimo 3 caracteres',
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Nome de usuário é obrigatório';
                  }
                  if (value.trim().length < 3) {
                    return 'Mínimo 3 caracteres';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),

              // Display Name
              TextFormField(
                controller: _displayNameController,
                decoration: const InputDecoration(
                  labelText: 'Nome de exibição *',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.badge),
                  helperText: 'Nome que aparecerá na interface',
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Nome de exibição é obrigatório';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),

              // Email
              TextFormField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: 'Email *',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.email),
                  helperText: 'Deve ser um email válido',
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Email é obrigatório';
                  }
                  if (!RegExp(r'^[\w\.\+\-]+@[\w\.\-]+\.\w+$').hasMatch(value)) {
                    return 'Email inválido';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),

              // Password
              TextFormField(
                controller: _passwordController,
                obscureText: !_showPassword,
                decoration: InputDecoration(
                  labelText: 'Senha *',
                  border: const OutlineInputBorder(),
                  prefixIcon: const Icon(Icons.lock),
                  helperText: 'Mínimo 8 caracteres',
                  suffixIcon: IconButton(
                    onPressed: () => setState(() => _showPassword = !_showPassword),
                    icon: Icon(_showPassword ? Icons.visibility_off : Icons.visibility),
                  ),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Senha é obrigatória';
                  }
                  if (value.length < 8) {
                    return 'Mínimo 8 caracteres';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),

              // Confirm Password
              TextFormField(
                controller: _confirmPasswordController,
                obscureText: !_showConfirmPassword,
                decoration: InputDecoration(
                  labelText: 'Confirmar senha *',
                  border: const OutlineInputBorder(),
                  prefixIcon: const Icon(Icons.lock_outline),
                  helperText: 'Repita a senha acima',
                  suffixIcon: IconButton(
                    onPressed: () => setState(() => _showConfirmPassword = !_showConfirmPassword),
                    icon: Icon(_showConfirmPassword ? Icons.visibility_off : Icons.visibility),
                  ),
                ),
                validator: (value) {
                  if (value != _passwordController.text) {
                    return 'As senhas não coincidem';
                  }
                  return null;
                },
              ),

              const SizedBox(height: 32),

              // Create Button
              ElevatedButton(
                onPressed: _isLoading ? null : _createUser,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _isLoading
                    ? const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    SizedBox(width: 12),
                    Text('Criando usuário...'),
                  ],
                )
                    : const Text(
                  'Criar Usuário',
                  style: TextStyle(fontSize: 16),
                ),
              ),

              const SizedBox(height: 12),

              // Cancel Button
              TextButton(
                onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
                child: const Text('Cancelar'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}