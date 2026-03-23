import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class IconButtonWidget extends StatelessWidget {
  const IconButtonWidget({
    super.key,
    required this.icon,
    required this.tooltip,
    this.onPressed,
    this.color,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(4),
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Icon(
              icon,
              size: 16,
              color: onPressed == null
                  ? SupabaseColors.textMuted.withOpacity(0.5)
                  : (color ?? SupabaseColors.textSecondary),
            ),
          ),
        ),
      ),
    );
  }
}
