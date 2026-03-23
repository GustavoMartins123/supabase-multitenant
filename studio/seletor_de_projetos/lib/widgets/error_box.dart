import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class ErrorBox extends StatelessWidget {
  const ErrorBox({
    super.key,
    required this.message,
    this.onRetry,
  });

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.error.withOpacity(0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.error.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: SupabaseColors.error, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: const TextStyle(color: SupabaseColors.error, fontSize: 12)),
          ),
          if (onRetry != null)
            TextButton(
              onPressed: onRetry,
              child: const Text('Tentar novamente', style: TextStyle(fontSize: 12)),
            ),
        ],
      ),
    );
  }
}
