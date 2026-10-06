import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../supabase_colors.dart';
import 'env_settings_metadata.dart';

class EnvSettingField extends StatelessWidget {
  const EnvSettingField({
    super.key,
    required this.meta,
    required this.value,
    required this.onChanged,
    required this.enabled,
    this.error,
  });

  final SettingMeta meta;
  final String? value;
  final ValueChanged<String> onChanged;
  final bool enabled;
  final String? error;

  bool _isTrue(String? value) {
    if (value == null) return false;
    final v = value.trim().toLowerCase();
    return v == 'true' || v == '1' || v == 'yes';
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';

    const units = ['KB', 'MB', 'GB', 'TB', 'PB'];
    double size = bytes.toDouble();
    int unitIndex = -1;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    if (unitIndex == 1 && size >= 1000) {
      size /= 1024;
      unitIndex++;
    }

    return '${size.toStringAsFixed(2)} ${units[unitIndex]}';
  }

  InputDecoration _fieldDecoration(String? error) {
    final borderColor =
        error == null ? SupabaseColors.border : SupabaseColors.error;
    return InputDecoration(
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      filled: true,
      fillColor: SupabaseColors.bg200,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(4),
        borderSide: BorderSide(color: borderColor),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(4),
        borderSide: BorderSide(color: borderColor),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(4),
        borderSide: BorderSide(
          color: error == null ? SupabaseColors.brand : SupabaseColors.error,
          width: 1.5,
        ),
      ),
    );
  }

  Widget _buildFieldError(String error) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: SizedBox(
        width: 180,
        child: Text(
          error,
          textAlign: TextAlign.right,
          style: const TextStyle(fontSize: 10, color: SupabaseColors.error),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final current = value ?? '';
    switch (meta.type) {
      case EnvFieldType.toggle:
        return SizedBox(
          height: 28,
          child: FittedBox(
            fit: BoxFit.contain,
            child: Switch(
              value: _isTrue(current),
              onChanged: enabled
                  ? (v) => onChanged(v ? 'true' : 'false')
                  : null,
              activeThumbColor: SupabaseColors.brand,
              inactiveThumbColor: SupabaseColors.textMuted,
              inactiveTrackColor: SupabaseColors.bg300,
            ),
          ),
        );
      case EnvFieldType.select:
        final options = kEnvSelectOptions[meta.key] ?? const {};
        return Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String>(
                initialValue: options.containsKey(current) ? current : null,
                isDense: true,
                isExpanded: true,
                dropdownColor: SupabaseColors.bg300,
                style: const TextStyle(
                  fontSize: 12,
                  color: SupabaseColors.textPrimary,
                ),
                icon: const Icon(
                  Icons.expand_more,
                  size: 18,
                  color: SupabaseColors.textMuted,
                ),
                decoration: _fieldDecoration(error),
                items: options.entries
                    .map((entry) => DropdownMenuItem(
                          value: entry.key,
                          child: Text(
                            entry.value,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12),
                          ),
                        ))
                    .toList(),
                onChanged:
                    enabled ? (v) => onChanged(v ?? '') : null,
              ),
            ),
            if (error != null) _buildFieldError(error!),
          ],
        );
      case EnvFieldType.number:
        final isFileSize = meta.key == 'FILE_SIZE_LIMIT';
        final bytes = int.tryParse(current) ?? 0;
        final formattedSize = _formatBytes(bytes);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 120,
                  height: 32,
                  child: TextField(
                    controller: TextEditingController(text: current)
                      ..selection = TextSelection.collapsed(
                        offset: current.length,
                      ),
                    enabled: enabled,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    onChanged: onChanged,
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: SupabaseColors.textPrimary,
                    ),
                    decoration: _fieldDecoration(error),
                  ),
                ),
                if (isFileSize && bytes > 0) ...[
                  const SizedBox(width: 8),
                  Text(
                    '≈ $formattedSize',
                    style: const TextStyle(
                      fontSize: 11,
                      color: SupabaseColors.textMuted,
                      fontFamily: 'monospace',
                    ),
                  ),
                ],
              ],
            ),
            if (error != null) _buildFieldError(error!),
          ],
        );
      case EnvFieldType.text:
        final formatters = <TextInputFormatter>[
          if (meta.key == 'PROJECT_MEM_LIMIT')
            FilteringTextInputFormatter.allow(RegExp(r'[0-9mMgG]'))
          else if (meta.key == 'PROJECT_CPUS')
            FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))
          else
            FilteringTextInputFormatter.allow(RegExp(r'[a-z0-9_,]')),
        ];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            SizedBox(
              width: 180,
              height: 32,
              child: TextField(
                controller: TextEditingController(text: current)
                  ..selection = TextSelection.collapsed(offset: current.length),
                enabled: enabled,
                inputFormatters: formatters,
                onChanged: onChanged,
                style: const TextStyle(
                  fontSize: 12,
                  fontFamily: 'monospace',
                  color: SupabaseColors.textPrimary,
                ),
                decoration: _fieldDecoration(error),
              ),
            ),
            if (error != null) _buildFieldError(error!),
          ],
        );
    }
  }
}
