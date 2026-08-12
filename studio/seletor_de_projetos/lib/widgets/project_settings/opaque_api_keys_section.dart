import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../data/project_repository.dart';
import '../../models/opaque_api_key.dart';
import '../../supabase_colors.dart';
import '../danger_button.dart';
import '../secondary_button.dart';
import '../section_widget.dart';

class OpaqueApiKeysSection extends ConsumerStatefulWidget {
  const OpaqueApiKeysSection({
    super.key,
    required this.projectRef,
    required this.canManage,
    required this.projectBusy,
  });

  final String projectRef;
  final bool canManage;
  final bool projectBusy;

  @override
  ConsumerState<OpaqueApiKeysSection> createState() =>
      _OpaqueApiKeysSectionState();
}

class _OpaqueApiKeysSectionState extends ConsumerState<OpaqueApiKeysSection> {
  bool _loading = true;
  bool _mutating = false;
  String? _error;
  Map<String, dynamic>? _migration;
  List<OpaqueApiKeySlot> _slots = const [];
  List<OpaqueApiKeyReveal> _reveals = const [];
  final Map<String, String> _revealedSecrets = {};

  bool get _disabled => _mutating || widget.projectBusy;

  @override
  void initState() {
    super.initState();
    if (widget.canManage) _reload();
  }

  void _snack(String message, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: color),
    );
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repository = ref.read(projectRepositoryProvider);
      final values = await Future.wait([
        repository.fetchOpaqueApiKeyMigration(widget.projectRef),
        repository.fetchOpaqueApiKeySlots(widget.projectRef),
        repository.fetchOpaqueApiKeyReveals(widget.projectRef),
      ]);
      if (!mounted) return;
      setState(() {
        _migration = values[0] as Map<String, dynamic>;
        _slots = values[1] as List<OpaqueApiKeySlot>;
        _reveals = values[2] as List<OpaqueApiKeyReveal>;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _mutate(Future<void> Function() operation) async {
    if (_disabled) return;
    setState(() => _mutating = true);
    try {
      await operation();
      await _reload();
    } catch (error) {
      _snack(
        error.toString().replaceFirst('Exception: ', ''),
        SupabaseColors.error,
      );
    } finally {
      if (mounted) setState(() => _mutating = false);
    }
  }

  Future<bool> _confirm(String title, String message) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            backgroundColor: SupabaseColors.bg200,
            title: Text(title),
            content: Text(message),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancelar'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Confirmar'),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _prepareMigration() async {
    final confirmed = await _confirm(
      'Preparar chaves opacas?',
      'Duas chaves ainda rejeitadas serao criadas. O gateway legado continua '
          'ativo ate o corte explicito.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref
          .read(projectRepositoryProvider)
          .prepareOpaqueApiKeyMigration(widget.projectRef);
      _snack('Migracao preparada. Revele e instale as duas chaves.',
          SupabaseColors.success);
    });
  }

  Future<void> _cutover() async {
    final confirmed = await _confirm(
      'Ativar somente chaves opacas?',
      'O gateway sera interrompido durante o corte. JWTs anon e service_role '
          'deixarao de funcionar como API key externa imediatamente.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref
          .read(projectRepositoryProvider)
          .cutoverOpaqueApiKeyMigration(widget.projectRef);
      _snack('Gateway ativado em modo opaque-only.', SupabaseColors.success);
    });
  }

  Future<void> _abortMigration() async {
    final confirmed = await _confirm(
      'Cancelar preparação opaca?',
      'As duas chaves preparadas serão destruídas. O gateway legado não será '
          'alterado e uma nova preparação poderá ser iniciada.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref
          .read(projectRepositoryProvider)
          .abortOpaqueApiKeyMigration(widget.projectRef);
      _revealedSecrets.clear();
      _snack('Preparação opaca cancelada.', SupabaseColors.success);
    });
  }

  Future<void> _claim(OpaqueApiKeyReveal reveal) async {
    await _mutate(() async {
      final secret = await ref
          .read(projectRepositoryProvider)
          .claimOpaqueApiKey(widget.projectRef, reveal.keyId);
      if (!mounted) return;
      setState(() => _revealedSecrets[reveal.keyId] = secret);
      await Clipboard.setData(ClipboardData(text: secret));
      _snack(
        'Chave revelada e copiada. Ela nao podera ser exibida novamente.',
        SupabaseColors.success,
      );
    });
  }

  Future<void> _confirmInstallation(
    OpaqueApiKeySlot slot,
    OpaqueApiKeyVersion key,
  ) async {
    final confirmed = await _confirm(
      'Confirmar instalacao?',
      'Confirme somente depois que o consumidor estiver configurado com a '
          'nova chave. O corte programado nao sera prorrogado.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref.read(projectRepositoryProvider).confirmOpaqueApiKeyInstallation(
            widget.projectRef,
            slot.id,
            key.id,
          );
      _snack('Instalacao confirmada.', SupabaseColors.success);
    });
  }

  Future<void> _rotate(OpaqueApiKeySlot slot) async {
    final confirmed = await _confirm(
      'Rotacionar ${slot.name} agora?',
      'A chave atual sera revogada sem periodo de sobreposicao. A nova chave '
          'sera mostrada uma unica vez.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      final issued = await ref
          .read(projectRepositoryProvider)
          .rotateOpaqueApiKeySlot(widget.projectRef, slot.id);
      if (!mounted) return;
      await _showIssuedKey(issued);
    });
  }

  Future<void> _disable(OpaqueApiKeySlot slot) async {
    final confirmed = await _confirm(
      'Revogar ${slot.name}?',
      'Todas as versoes desse slot serao revogadas. Os demais slots nao serao alterados.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref
          .read(projectRepositoryProvider)
          .disableOpaqueApiKeySlot(widget.projectRef, slot.id);
    });
  }

  Future<void> _toggleAutomatic(OpaqueApiKeySlot slot, bool enabled) async {
    await _mutate(() async {
      await ref.read(projectRepositoryProvider).updateOpaqueApiKeySlot(
            widget.projectRef,
            slot.id,
            automaticRotationEnabled: enabled,
          );
    });
  }

  Future<void> _editExpirationPolicy(OpaqueApiKeySlot slot) async {
    final selection = await showDialog<_ExpirationPolicySelection>(
      context: context,
      builder: (context) => _ExpirationPolicyDialog(
        initialDays: slot.rotationIntervalDays,
      ),
    );
    if (selection == null ||
        selection.days == slot.rotationIntervalDays ||
        !mounted) {
      return;
    }
    final neverExpires = selection.days == null;
    final confirmed = await _confirm(
      neverExpires ? 'Remover expiração temporal?' : 'Alterar expiração?',
      neverExpires
          ? 'A chave ativa continuará válida até rotação, revogação ou disable '
              'do slot. Uma rotação automática pendente ainda não efetiva '
              'será cancelada.'
          : 'A chave ativa passará a expirar ${selection.days} dias após esta '
              'alteração. Uma chave já vencida não será reativada.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref.read(projectRepositoryProvider).updateOpaqueApiKeySlot(
            widget.projectRef,
            slot.id,
            automaticRotationEnabled: neverExpires ? false : null,
            expirationPolicy: OpaqueApiKeyExpirationPolicyUpdate(
              selection.days,
            ),
          );
      _snack(
        neverExpires
            ? 'A chave ativa agora não expira.'
            : 'Expiração temporal atualizada.',
        SupabaseColors.success,
      );
    });
  }

  Future<void> _cancelPendingRotation(OpaqueApiKeySlot slot) async {
    final confirmed = await _confirm(
      'Cancelar rotação pendente?',
      'A chave pendente será revogada. A chave ativa continuará com sua data '
          'de expiração atual.',
    );
    if (!confirmed) return;
    await _mutate(() async {
      await ref
          .read(projectRepositoryProvider)
          .cancelOpaqueApiKeyRotation(widget.projectRef, slot.id);
      _snack('Rotação pendente cancelada.', SupabaseColors.success);
    });
  }

  Future<void> _createSlot() async {
    final issued = await showDialog<IssuedOpaqueApiKey>(
      context: context,
      builder: (context) => _CreateOpaqueSlotDialog(
        projectRef: widget.projectRef,
        repository: ref.read(projectRepositoryProvider),
      ),
    );
    if (issued == null || !mounted) return;
    await _showIssuedKey(issued);
    await _reload();
  }

  Future<void> _showIssuedKey(IssuedOpaqueApiKey issued) async {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: SupabaseColors.bg200,
        title: const Text('Copie a API key agora'),
        content: SizedBox(
          width: 560,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'O valor completo nao sera armazenado nem mostrado novamente.',
                style: TextStyle(color: SupabaseColors.warning),
              ),
              const SizedBox(height: 8),
              Text(
                issued.expiresAt == null
                    ? 'Lifetime da credencial: Não expira'
                    : 'Lifetime da credencial: expira em '
                        '${_date(issued.expiresAt!)}',
                style: const TextStyle(
                  color: SupabaseColors.textMuted,
                  fontSize: 11,
                ),
              ),
              const SizedBox(height: 12),
              SelectableText(
                issued.apiKey,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: issued.apiKey));
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('Copiar e fechar'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.canManage) {
      return const SectionWidget(
        title: 'API KEYS OPACAS',
        child: Text(
          'Somente administradores do projeto podem consultar ou gerenciar API keys.',
          style: TextStyle(color: SupabaseColors.textMuted),
        ),
      );
    }
    return SectionWidget(
      title: 'API KEYS OPACAS',
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_error!,
                        style: const TextStyle(color: SupabaseColors.error)),
                    const SizedBox(height: 8),
                    SecondaryButton(
                        label: 'Tentar novamente', onPressed: _reload),
                  ],
                )
              : _buildContent(),
    );
  }

  Widget _buildContent() {
    final status = _migration!['status'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _statusBanner(status.toString()),
        if (status == 'legacy') ...[
          const SizedBox(height: 12),
          SecondaryButton(
            label: 'Preparar migracao opaca',
            icon: Icons.security_rounded,
            onPressed: _disabled ? null : _prepareMigration,
          ),
        ],
        if (status == 'prepared') ...[
          const SizedBox(height: 8),
          DangerButton(
            label: 'Cancelar preparação',
            icon: Icons.undo_rounded,
            onPressed: _disabled ? null : _abortMigration,
          ),
        ],
        if (_reveals.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('REVELACOES PENDENTES', style: _captionStyle),
          const SizedBox(height: 8),
          ..._reveals.map(_revealCard),
        ],
        if (_slots.isNotEmpty) ...[
          const SizedBox(height: 16),
          ..._slots.map(_slotCard),
        ],
        if (status == 'prepared' || status == 'gateway_recovery_required') ...[
          const SizedBox(height: 12),
          SecondaryButton(
            label: status == 'gateway_recovery_required'
                ? 'Recuperar gateway opaco'
                : 'Executar corte opaco',
            icon: Icons.swap_horiz_rounded,
            onPressed: _disabled ||
                    (status == 'prepared' && !_allMigrationKeysConfirmed)
                ? null
                : _cutover,
          ),
        ],
        if (status == 'active') ...[
          const SizedBox(height: 12),
          SecondaryButton(
            label: 'Criar slot',
            icon: Icons.add_rounded,
            onPressed: _disabled ? null : _createSlot,
          ),
        ],
      ],
    );
  }

  bool get _allMigrationKeysConfirmed {
    final pending = _migration!['pending_key_count'];
    final confirmed = _migration!['confirmed_pending_key_count'];
    return pending is int && pending == 2 && confirmed == 2;
  }

  Widget _statusBanner(String status) {
    final (label, color) = switch (status) {
      'active' => ('Gateway opaque-only ativo', SupabaseColors.success),
      'prepared' => (
          'Migracao preparada; JWT legado ainda esta ativo',
          SupabaseColors.warning
        ),
      'gateway_recovery_required' => (
          'Corte incompleto; recuperacao obrigatoria',
          SupabaseColors.error
        ),
      'legacy' => (
          'Projeto ainda usa API keys JWT legadas',
          SupabaseColors.warning
        ),
      _ => ('Estado de migracao invalido', SupabaseColors.error),
    };
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 12)),
    );
  }

  Widget _revealCard(OpaqueApiKeyReveal reveal) {
    final secret = _revealedSecrets[reveal.keyId];
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: _boxDecoration,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${reveal.slotName} · ${reveal.kind}', style: _titleStyle),
          Text(
            'Disponivel ate ${_date(reveal.expiresAt)}',
            style:
                const TextStyle(color: SupabaseColors.textMuted, fontSize: 11),
          ),
          if (secret != null) ...[
            const SizedBox(height: 8),
            SelectableText(secret,
                style: const TextStyle(fontFamily: 'monospace')),
          ],
          const SizedBox(height: 8),
          SecondaryButton(
            label: secret == null ? 'Revelar e copiar' : 'Copiar novamente',
            icon: Icons.copy_rounded,
            onPressed: _disabled
                ? null
                : secret == null
                    ? () => _claim(reveal)
                    : () => Clipboard.setData(ClipboardData(text: secret)),
          ),
        ],
      ),
    );
  }

  Widget _slotCard(OpaqueApiKeySlot slot) {
    final pending = slot.keys.where((key) => key.status == 'pending').toList();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: _boxDecoration,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(slot.name, style: _titleStyle)),
              Text(slot.kind,
                  style: const TextStyle(color: SupabaseColors.brand)),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${slot.allowedServices.join(', ')} · Expiração: '
            '${_expirationLabel(slot.rotationIntervalDays)}',
            style:
                const TextStyle(color: SupabaseColors.textMuted, fontSize: 11),
          ),
          if (slot.automaticRotationLastError != null) ...[
            const SizedBox(height: 6),
            Text(
              slot.automaticRotationLastError!,
              style: const TextStyle(color: SupabaseColors.error, fontSize: 11),
            ),
          ],
          const SizedBox(height: 8),
          ...slot.keys.where((key) => key.status != 'revoked').map(
                (key) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    '${key.tokenHint} · ${key.status} · '
                    '${key.expiresAt == null ? 'Não expira' : 'expira ${_date(key.expiresAt!)}'}'
                    '${key.lastUsedAt == null ? '' : ' · uso ${_date(key.lastUsedAt!)}'}',
                    style: TextStyle(
                      color: key.currentlyAccepted
                          ? SupabaseColors.success
                          : SupabaseColors.textSecondary,
                      fontSize: 11,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ),
          for (final key in pending)
            if (key.revealedAt != null && key.confirmedAt == null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: SecondaryButton(
                  label: 'Confirmar instalacao de ${key.tokenHint}',
                  icon: Icons.check_rounded,
                  onPressed:
                      _disabled ? null : () => _confirmInstallation(slot, key),
                ),
              ),
          const Divider(color: SupabaseColors.border),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            value: slot.automaticRotationEnabled,
            onChanged: _disabled || slot.rotationIntervalDays == null
                ? null
                : (value) => _toggleAutomatic(slot, value),
            title: const Text('Rotacao automatica',
                style: TextStyle(fontSize: 12)),
            subtitle: slot.rotationIntervalDays == null
                ? const Text(
                    'Defina uma expiração temporal para habilitar.',
                    style: TextStyle(fontSize: 11),
                  )
                : null,
          ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              SecondaryButton(
                label: 'Expiração: '
                    '${_expirationLabel(slot.rotationIntervalDays)}',
                icon: Icons.timer_outlined,
                onPressed: _disabled ? null : () => _editExpirationPolicy(slot),
              ),
              SecondaryButton(
                label: 'Rotacionar agora',
                icon: Icons.refresh_rounded,
                onPressed: _disabled || pending.isNotEmpty
                    ? null
                    : () => _rotate(slot),
              ),
              if (pending.isNotEmpty && _migration!['status'] == 'active')
                SecondaryButton(
                  label: 'Cancelar rotação pendente',
                  icon: Icons.cancel_outlined,
                  onPressed:
                      _disabled ? null : () => _cancelPendingRotation(slot),
                ),
              DangerButton(
                label: 'Revogar slot',
                icon: Icons.block_rounded,
                onPressed: _disabled ? null : () => _disable(slot),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _date(DateTime value) =>
      DateFormat('dd/MM/yyyy HH:mm').format(value.toLocal());

  static const _captionStyle = TextStyle(
    color: SupabaseColors.textMuted,
    fontSize: 10,
    fontWeight: FontWeight.w600,
  );
  static const _titleStyle = TextStyle(
    color: SupabaseColors.textPrimary,
    fontSize: 13,
    fontWeight: FontWeight.w600,
  );
  static final _boxDecoration = BoxDecoration(
    color: SupabaseColors.bg300,
    border: Border.all(color: SupabaseColors.border),
    borderRadius: BorderRadius.circular(6),
  );
}

class _CreateOpaqueSlotDialog extends StatefulWidget {
  const _CreateOpaqueSlotDialog({
    required this.projectRef,
    required this.repository,
  });

  final String projectRef;
  final ProjectRepository repository;

  @override
  State<_CreateOpaqueSlotDialog> createState() =>
      _CreateOpaqueSlotDialogState();
}

class _CreateOpaqueSlotDialogState extends State<_CreateOpaqueSlotDialog> {
  static const _services = [
    'auth',
    'rest',
    'graphql',
    'realtime',
    'storage',
    'functions',
  ];
  final _name = TextEditingController();
  final _selectedServices = <String>{..._services};
  String _kind = 'publishable';
  bool _automatic = true;
  int? _interval = 90;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _chooseExpirationPolicy() async {
    final selection = await showDialog<_ExpirationPolicySelection>(
      context: context,
      builder: (context) => _ExpirationPolicyDialog(initialDays: _interval),
    );
    if (selection == null || !mounted) return;
    setState(() {
      _interval = selection.days;
      if (_interval == null) _automatic = false;
    });
  }

  Future<void> _submit() async {
    final name = _name.text;
    if (!RegExp(r'^[a-z][a-z0-9_-]{2,39}$').hasMatch(name)) {
      setState(() => _error = 'Use 3-40 caracteres: a-z, 0-9, _ ou -.');
      return;
    }
    if (_selectedServices.isEmpty) {
      setState(() => _error = 'Selecione ao menos um servico.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final issued = await widget.repository.createOpaqueApiKeySlot(
        widget.projectRef,
        name: name,
        kind: _kind,
        allowedServices: _selectedServices.toList()..sort(),
        automaticRotationEnabled: _automatic,
        rotationIntervalDays: _interval,
      );
      if (mounted) Navigator.pop(context, issued);
    } catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = error.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: SupabaseColors.bg200,
      title: const Text('Novo slot de API key'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _name,
                decoration:
                    const InputDecoration(labelText: 'Nome do consumidor'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(labelText: 'Tipo'),
                items: const [
                  DropdownMenuItem(
                      value: 'publishable', child: Text('Publishable')),
                  DropdownMenuItem(value: 'secret', child: Text('Secret')),
                ],
                onChanged:
                    _saving ? null : (value) => setState(() => _kind = value!),
              ),
              const SizedBox(height: 12),
              const Text('Servicos permitidos',
                  style: _OpaqueApiKeysSectionState._captionStyle),
              Wrap(
                spacing: 6,
                children: _services
                    .map(
                      (service) => FilterChip(
                        label: Text(service),
                        selected: _selectedServices.contains(service),
                        onSelected: _saving
                            ? null
                            : (selected) => setState(() {
                                  if (selected) {
                                    _selectedServices.add(service);
                                  } else {
                                    _selectedServices.remove(service);
                                  }
                                }),
                      ),
                    )
                    .toList(),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                value: _automatic,
                onChanged: _saving || _interval == null
                    ? null
                    : (value) => setState(() => _automatic = value),
                title: const Text('Rotacao automatica'),
                subtitle: _interval == null
                    ? const Text(
                        'Indisponível para chaves sem expiração temporal.',
                      )
                    : null,
              ),
              SecondaryButton(
                label: 'Expiração da chave: ${_expirationLabel(_interval)}',
                icon: Icons.timer_outlined,
                onPressed: _saving ? null : _chooseExpirationPolicy,
              ),
              if (_error != null) ...[
                const SizedBox(height: 10),
                Text(_error!,
                    style: const TextStyle(color: SupabaseColors.error)),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        TextButton(
          onPressed: _saving ? null : _submit,
          child: Text(_saving ? 'Criando...' : 'Criar e revelar'),
        ),
      ],
    );
  }
}

class _ExpirationPolicySelection {
  const _ExpirationPolicySelection(this.days);

  final int? days;
}

String _expirationLabel(int? days) =>
    days == null ? 'Não expira' : '$days dias';

class _ExpirationPolicyDialog extends StatefulWidget {
  const _ExpirationPolicyDialog({required this.initialDays});

  final int? initialDays;

  @override
  State<_ExpirationPolicyDialog> createState() =>
      _ExpirationPolicyDialogState();
}

class _ExpirationPolicyDialogState extends State<_ExpirationPolicyDialog> {
  static const _presetDays = {90, 180, 365};
  late String _choice;
  late final TextEditingController _customDays;
  String? _error;

  @override
  void initState() {
    super.initState();
    final initialDays = widget.initialDays;
    if (initialDays == null) {
      _choice = 'never';
    } else if (_presetDays.contains(initialDays)) {
      _choice = initialDays.toString();
    } else {
      _choice = 'custom';
    }
    _customDays = TextEditingController(
      text: initialDays == null || _presetDays.contains(initialDays)
          ? ''
          : initialDays.toString(),
    );
  }

  @override
  void dispose() {
    _customDays.dispose();
    super.dispose();
  }

  void _submit() {
    int? days;
    if (_choice != 'never') {
      days = _choice == 'custom'
          ? int.tryParse(_customDays.text)
          : int.parse(_choice);
      if (days == null || days < 1 || days > 3650) {
        setState(() => _error = 'Informe um intervalo entre 1 e 3650 dias.');
        return;
      }
    }
    Navigator.pop(context, _ExpirationPolicySelection(days));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: SupabaseColors.bg200,
      title: const Text('Expiração da chave'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'O lifetime da credencial não altera a janela curta de '
              'revelação única nem o lifetime de JWTs e sessões.',
              style: TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _choice,
              decoration: const InputDecoration(labelText: 'Política'),
              items: const [
                DropdownMenuItem(value: 'never', child: Text('Não expira')),
                DropdownMenuItem(value: '90', child: Text('90 dias')),
                DropdownMenuItem(value: '180', child: Text('180 dias')),
                DropdownMenuItem(value: '365', child: Text('365 dias')),
                DropdownMenuItem(value: 'custom', child: Text('Personalizado')),
              ],
              onChanged: (value) => setState(() {
                _choice = value!;
                _error = null;
              }),
            ),
            if (_choice == 'custom') ...[
              const SizedBox(height: 12),
              TextField(
                controller: _customDays,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(
                  labelText: 'Intervalo em dias',
                  hintText: '1 a 3650',
                ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(
                _error!,
                style: const TextStyle(color: SupabaseColors.error),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        TextButton(onPressed: _submit, child: const Text('Aplicar')),
      ],
    );
  }
}
