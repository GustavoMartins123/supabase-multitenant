import 'package:web/web.dart' as web;

import 'package:flutter/material.dart';

import 'createUserDialog.dart';
import 'supabase_colors.dart';

class BootstrapAdminPage extends StatefulWidget {
  const BootstrapAdminPage({super.key});

  @override
  State<BootstrapAdminPage> createState() => _BootstrapAdminPageState();
}

class _BootstrapAdminPageState extends State<BootstrapAdminPage> {
  bool _dialogOpen = false;

  String _loginUrl() {
    final location = web.window.location;
    return '${location.protocol}//${location.hostname}:9091/login';
  }

  Future<void> _openCreateAdmin() async {
    if (_dialogOpen) return;
    setState(() => _dialogOpen = true);

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => CreateUserDialog(
        bootstrapMode: true,
        onUserCreated: () {
          web.window.location.href = _loginUrl();
        },
      ),
    );

    if (mounted) setState(() => _dialogOpen = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SupabaseColors.bg100,
      body: Center(
        child: Container(
          width: 420,
          margin: const EdgeInsets.all(24),
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: SupabaseColors.bg200,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: SupabaseColors.border),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: SupabaseColors.brand.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(
                      Icons.admin_panel_settings_rounded,
                      color: SupabaseColors.brand,
                      size: 22,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Configuração Inicial',
                      style: TextStyle(
                        color: SupabaseColors.textPrimary,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              const Text(
                'Nenhum administrador foi criado ainda.',
                style: TextStyle(
                  color: SupabaseColors.textSecondary,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 20),
              ElevatedButton.icon(
                onPressed: _openCreateAdmin,
                icon: const Icon(Icons.person_add_alt_1_rounded, size: 18),
                label: const Text('Criar administrador'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: SupabaseColors.brand,
                  foregroundColor: SupabaseColors.bg100,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
