import 'package:flutter/material.dart';
import 'package:seletor_de_projetos/supabase_colors.dart';

class ActionButton extends StatelessWidget {
  const ActionButton({
    super.key,
    required this.icon,
    required this.label,
    required this.color,
    this.onPressed,
    this.busy = false,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: onPressed == null
                ? SupabaseColors.bg300
                : color.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: onPressed == null
                  ? SupabaseColors.border
                  : color.withValues(alpha: 0.3),
            ),
          ),
          child: Column(
            children: [
              if (busy)
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation(color),
                  ),
                )
              else
                Icon(
                  icon,
                  color: onPressed == null ? SupabaseColors.textMuted : color,
                  size: 18,
                ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                  color: onPressed == null ? SupabaseColors.textMuted : color,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
