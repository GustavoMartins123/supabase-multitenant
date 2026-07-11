import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../data/project_repository.dart';
import '../../models/project_user_telemetry.dart';
import '../../supabase_colors.dart';
import '../section_widget.dart';

class UserTelemetrySection extends ConsumerStatefulWidget {
  const UserTelemetrySection({super.key, required this.projectRef});

  final String projectRef;

  @override
  ConsumerState<UserTelemetrySection> createState() =>
      _UserTelemetrySectionState();
}

class _UserTelemetrySectionState extends ConsumerState<UserTelemetrySection> {
  String _period = '24h';
  DateTimeRange? _customRange;
  ProjectUserTelemetry? _telemetry;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      DateTime? start;
      DateTime? end;
      if (_period == 'custom' && _customRange != null) {
        final now = DateTime.now();
        final includesToday = _customRange!.end.year == now.year &&
            _customRange!.end.month == now.month &&
            _customRange!.end.day == now.day;
        start = DateTime(
          _customRange!.start.year,
          _customRange!.start.month,
          _customRange!.start.day,
        );
        end = includesToday
            ? now
            : DateTime(
                _customRange!.end.year,
                _customRange!.end.month,
                _customRange!.end.day + 1,
              );
      }
      final telemetry =
          await ref.read(projectRepositoryProvider).fetchProjectUserTelemetry(
                widget.projectRef,
                period: _period,
                start: start,
                end: end,
              );
      if (!mounted) return;
      setState(() => _telemetry = telemetry);
    } catch (err) {
      if (!mounted) return;
      setState(() {
        _telemetry = null;
        _error = err.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _selectPeriod(String period) async {
    if (period != 'custom') {
      setState(() => _period = period);
      await _load();
      return;
    }

    final now = DateTime.now();
    final selected = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 1, now.month, now.day),
      lastDate: now,
      initialDateRange: _customRange,
      helpText: 'Selecionar periodo da telemetria',
      saveText: 'Aplicar',
    );
    if (selected == null || !mounted) return;
    setState(() {
      _period = 'custom';
      _customRange = selected;
    });
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return SectionWidget(
      title: 'TELEMETRIA DE USUARIOS',
      trailing: IconButton(
        visualDensity: VisualDensity.compact,
        tooltip: 'Atualizar',
        onPressed: _loading ? null : _load,
        icon: const Icon(Icons.refresh_rounded, size: 18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _periodChip('24h', '24 horas'),
              _periodChip('7d', '7 dias'),
              _periodChip('30d', '30 dias'),
              _periodChip('custom', 'Personalizado'),
            ],
          ),
          if (_period == 'custom' && _customRange != null) ...[
            const SizedBox(height: 10),
            Text(
              '${DateFormat('dd/MM/yyyy').format(_customRange!.start)} - '
              '${DateFormat('dd/MM/yyyy').format(_customRange!.end)}',
              style: const TextStyle(
                color: SupabaseColors.textSecondary,
                fontSize: 12,
              ),
            ),
          ],
          const SizedBox(height: 16),
          if (_loading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: SupabaseColors.brand,
                ),
              ),
            )
          else if (_error != null)
            _buildError()
          else if (_telemetry != null)
            _buildTelemetry(_telemetry!),
        ],
      ),
    );
  }

  Widget _periodChip(String value, String label) {
    final selected = _period == value;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => _selectPeriod(value),
      selectedColor: SupabaseColors.brand.withValues(alpha: 0.18),
      backgroundColor: SupabaseColors.bg300,
      side: BorderSide(
        color: selected ? SupabaseColors.brand : SupabaseColors.border,
      ),
      labelStyle: TextStyle(
        color: selected ? SupabaseColors.brand : SupabaseColors.textSecondary,
        fontSize: 12,
      ),
    );
  }

  Widget _buildError() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.error.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.error.withValues(alpha: 0.4)),
      ),
      child: Text(
        _error!,
        style: const TextStyle(color: SupabaseColors.error, fontSize: 12),
      ),
    );
  }

  Widget _buildTelemetry(ProjectUserTelemetry telemetry) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: _metricCard(
                icon: Icons.people_alt_outlined,
                label: 'Usuarios ativos',
                value: telemetry.activeUsers.toString(),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _metricCard(
                icon: Icons.login_rounded,
                label: 'Sessoes registradas',
                value: telemetry.totalSessions.toString(),
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        if (telemetry.users.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Center(
              child: Text(
                'Nenhum login encontrado no periodo.',
                style: TextStyle(color: SupabaseColors.textMuted),
              ),
            ),
          )
        else
          Container(
            height: 280,
            decoration: BoxDecoration(
              color: SupabaseColors.bg300,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SupabaseColors.border),
            ),
            child: ListView.separated(
              itemCount: telemetry.users.length,
              separatorBuilder: (_, __) =>
                  const Divider(height: 1, color: SupabaseColors.border),
              itemBuilder: (_, index) => _userRow(telemetry.users[index]),
            ),
          ),
        const SizedBox(height: 10),
        const Text(
          'A contagem usa os registros atuais de auth.sessions. Sessoes '
          'expiradas ou removidas podem nao aparecer no total.',
          style: TextStyle(
            color: SupabaseColors.textMuted,
            fontSize: 11,
            height: 1.4,
          ),
        ),
      ],
    );
  }

  Widget _metricCard({
    required IconData icon,
    required String label,
    required String value,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.bg300,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Row(
        children: [
          Icon(icon, color: SupabaseColors.brand, size: 20),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: SupabaseColors.textPrimary,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text(
                label,
                style: const TextStyle(
                  color: SupabaseColors.textMuted,
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _userRow(ProjectTelemetryUser user) {
    final lastLogin = user.lastLoginAt == null
        ? 'Ultimo login indisponivel'
        : 'Ultimo login: ${DateFormat('dd/MM/yyyy HH:mm').format(user.lastLoginAt!.toLocal())}';
    return ListTile(
      dense: true,
      leading: const CircleAvatar(
        radius: 15,
        backgroundColor: SupabaseColors.surface300,
        child: Icon(
          Icons.person_outline_rounded,
          color: SupabaseColors.textSecondary,
          size: 17,
        ),
      ),
      title: Text(
        user.displayName,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(
          color: SupabaseColors.textPrimary,
          fontSize: 12,
        ),
      ),
      subtitle: Text(
        lastLogin,
        style: const TextStyle(color: SupabaseColors.textMuted, fontSize: 11),
      ),
      trailing: Tooltip(
        message: 'Sessoes no periodo',
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: SupabaseColors.brand.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            user.sessionCount.toString(),
            style: const TextStyle(
              color: SupabaseColors.brand,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}
