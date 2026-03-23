import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class CloseButtonWidget extends StatelessWidget {
  const CloseButtonWidget({super.key, required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(4),
        child: const Padding(
          padding: EdgeInsets.all(6),
          child: Icon(
            Icons.close_rounded,
            size: 18,
            color: SupabaseColors.textMuted,
          ),
        ),
      ),
    );
  }
}
