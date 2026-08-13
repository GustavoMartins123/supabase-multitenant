import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../models/opaque_api_key.dart';
import '../../providers/opaque_api_keys_provider.dart';
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
  OpaqueApiKeysController get _controller =>
      ref.read(opaqueApiKeysProvider(widget.projectRef).notifier);

  bool _disabled(OpaqueApiKeysState state) =>
      widget.projectBusy || state.actionsLocked;

  void _snack(String message, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: color),
    );
  }

  void _showError(Object error) {
    _snack(opaqueApiKeyErrorMessage(error), SupabaseColors.error);
  }

  Future<void> _runCommand(
    Future<void> Function() command, {
    String? successMessage,
  }) async {
    try {
      await command();
      if (successMessage != null) {
        _snack(successMessage, SupabaseColors.success);
      }
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _refreshAfterSecret() async {
    try {
      await _controller.refresh();
    } catch (error) {
      _showError(error);
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
    await _runCommand(
      _controller.prepareMigration,
      successMessage: 'Migracao preparada. Revele e instale as duas chaves.',
    );
  }

  Future<void> _cutover() async {
    final confirmed = await _confirm(
      'Ativar somente chaves opacas?',
      'O gateway sera interrompido durante o corte. JWTs anon e service_role '
          'deixarao de funcionar como API key externa imediatamente.',
    );
    if (!confirmed) return;
    await _runCommand(
      _controller.cutoverMigration,
      successMessage: 'Gateway ativado em modo opaque-only.',
    );
  }

  Future<void> _abortMigration() async {
    final confirmed = await _confirm(
      'Cancelar preparação opaca?',
      'As duas chaves preparadas serão destruídas. O gateway legado não será '
          'alterado e uma nova preparação poderá ser iniciada.',
    );
    if (!confirmed) return;
    await _runCommand(
      _controller.abortMigration,
      successMessage: 'Preparação opaca cancelada.',
    );
  }

  Future<void> _claim(OpaqueApiKeyReveal reveal) async {
    try {
      final secret = await _controller.claimReveal(reveal.keyId);
      if (!mounted) return;

      var copied = false;
      String? clipboardError;
      try {
        await Clipboard.setData(ClipboardData(text: secret));
        copied = true;
      } catch (error) {
        clipboardError = opaqueApiKeyErrorMessage(error);
      }
      if (!mounted) return;

      final copiedBeforeClose = await showDialog<bool>(
            context: context,
            barrierDismissible: false,
            builder: (context) => _ClaimedOpaqueApiKeyDialog(
              secret: secret,
              reveal: reveal,
              initiallyCopied: copied,
              initialClipboardError: clipboardError,
            ),
          ) ??
          copied;
      if (!mounted) return;
      _snack(
        copiedBeforeClose
            ? 'Chave revelada e copiada. Ela não poderá ser exibida novamente.'
            : 'Chave revelada e consumida no servidor. O valor não foi copiado.',
        copiedBeforeClose ? SupabaseColors.success : SupabaseColors.warning,
      );
      unawaited(_refreshAfterSecret());
    } catch (error) {
      _showError(error);
    }
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
    await _runCommand(
      () => _controller.confirmInstallation(slot.id, key.id),
      successMessage: 'Instalacao confirmada.',
    );
  }

  Future<void> _rotate(OpaqueApiKeySlot slot) async {
    final confirmed = await _confirm(
      'Rotacionar ${slot.name} agora?',
      'A chave atual sera revogada sem periodo de sobreposicao. A nova chave '
          'sera mostrada uma unica vez.',
    );
    if (!confirmed) return;
    try {
      final issued = await _controller.rotateSlot(slot.id);
      if (!mounted) return;
      await _showIssuedKey(issued);
      if (mounted) unawaited(_refreshAfterSecret());
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _disable(OpaqueApiKeySlot slot) async {
    final confirmed = await _confirm(
      'Revogar ${slot.name}?',
      'Todas as versoes desse slot serao revogadas. Os demais slots nao serao alterados.',
    );
    if (!confirmed) return;
    await _runCommand(() => _controller.disableSlot(slot.id));
  }

  Future<void> _toggleAutomatic(OpaqueApiKeySlot slot, bool enabled) async {
    await _runCommand(
      () => _controller.updateAutomaticRotation(slot.id, enabled),
    );
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
    await _runCommand(
      () => _controller.updateExpirationPolicy(slot.id, selection.days),
      successMessage: neverExpires
          ? 'A chave ativa agora não expira.'
          : 'Expiração temporal atualizada.',
    );
  }

  Future<void> _cancelPendingRotation(OpaqueApiKeySlot slot) async {
    final confirmed = await _confirm(
      'Cancelar rotação pendente?',
      'A chave pendente será revogada. A chave ativa continuará com sua data '
          'de expiração atual.',
    );
    if (!confirmed) return;
    await _runCommand(
      () => _controller.cancelPendingRotation(slot.id),
      successMessage: 'Rotação pendente cancelada.',
    );
  }

  Future<void> _createSlot() async {
    final draft = await showDialog<_CreateOpaqueSlotDraft>(
      context: context,
      builder: (context) => const _CreateOpaqueSlotDialog(),
    );
    if (draft == null || !mounted) return;
    try {
      final issued = await _controller.createSlot(
        name: draft.name,
        kind: draft.kind,
        allowedServices: draft.allowedServices,
        automaticRotationEnabled: draft.automaticRotationEnabled,
        rotationIntervalDays: draft.rotationIntervalDays,
      );
      if (!mounted) return;
      await _showIssuedKey(issued);
      if (mounted) unawaited(_refreshAfterSecret());
    } catch (error) {
      _showError(error);
    }
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
    final asyncState = ref.watch(opaqueApiKeysProvider(widget.projectRef));
    return SectionWidget(
      title: 'API KEYS OPACAS',
      child: asyncState.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              opaqueApiKeyErrorMessage(error),
              style: const TextStyle(color: SupabaseColors.error),
            ),
            const SizedBox(height: 8),
            SecondaryButton(
              label: 'Tentar novamente',
              onPressed: () =>
                  ref.invalidate(opaqueApiKeysProvider(widget.projectRef)),
            ),
          ],
        ),
        data: _buildContent,
      ),
    );
  }

  Widget _buildContent(OpaqueApiKeysState state) {
    final status = state.migration['status'];
    final disabled = _disabled(state);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _statusBanner(status.toString()),
        if (state.isRefreshing || state.hasProjectOperation) ...[
          const SizedBox(height: 8),
          const LinearProgressIndicator(
            key: ValueKey('opaque-api-keys-project-progress'),
            minHeight: 2,
          ),
        ],
        if (state.synchronizationError != null) ...[
          const SizedBox(height: 8),
          _synchronizationError(state),
        ],
        if (status == 'legacy') ...[
          const SizedBox(height: 12),
          SecondaryButton(
            label: 'Preparar migracao opaca',
            icon: Icons.security_rounded,
            onPressed: disabled ? null : _prepareMigration,
          ),
        ],
        if (status == 'prepared') ...[
          const SizedBox(height: 8),
          DangerButton(
            label: 'Cancelar preparação',
            icon: Icons.undo_rounded,
            onPressed: disabled ? null : _abortMigration,
          ),
        ],
        if (state.reveals.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('REVELACOES PENDENTES', style: _captionStyle),
          const SizedBox(height: 8),
          ...state.reveals.map((reveal) => _revealCard(state, reveal)),
        ],
        if (state.slots.isNotEmpty) ...[
          const SizedBox(height: 16),
          ...state.slots.map((slot) => _slotCard(state, slot)),
        ],
        if (status == 'prepared' || status == 'gateway_recovery_required') ...[
          const SizedBox(height: 12),
          SecondaryButton(
            label: status == 'gateway_recovery_required'
                ? 'Recuperar gateway opaco'
                : 'Executar corte opaco',
            icon: Icons.swap_horiz_rounded,
            onPressed: disabled ||
                    (status == 'prepared' && !_allMigrationKeysConfirmed(state))
                ? null
                : _cutover,
          ),
        ],
        if (status == 'active') ...[
          const SizedBox(height: 12),
          SecondaryButton(
            label: 'Criar slot',
            icon: Icons.add_rounded,
            onPressed: disabled ? null : _createSlot,
          ),
        ],
      ],
    );
  }

  bool _allMigrationKeysConfirmed(OpaqueApiKeysState state) {
    final pending = state.migration['pending_key_count'];
    final confirmed = state.migration['confirmed_pending_key_count'];
    return pending is int && pending == 2 && confirmed == 2;
  }

  Widget _synchronizationError(OpaqueApiKeysState state) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: SupabaseColors.error.withValues(alpha: 0.12),
        border: Border.all(color: SupabaseColors.error),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            state.synchronizationError!,
            style: const TextStyle(color: SupabaseColors.error, fontSize: 12),
          ),
          const SizedBox(height: 8),
          SecondaryButton(
            label: state.isRefreshing
                ? 'Sincronizando...'
                : 'Sincronizar novamente',
            icon: Icons.sync_rounded,
            onPressed: state.isRefreshing
                ? null
                : () => unawaited(_refreshAfterSecret()),
          ),
        ],
      ),
    );
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

  Widget _revealCard(
    OpaqueApiKeysState state,
    OpaqueApiKeyReveal reveal,
  ) {
    final busy = state.isRevealBusy(reveal.keyId);
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
          if (busy) ...[
            const SizedBox(height: 8),
            LinearProgressIndicator(
              key: ValueKey('opaque-reveal-progress-${reveal.keyId}'),
              minHeight: 2,
            ),
          ],
          const SizedBox(height: 8),
          SecondaryButton(
            label: busy ? 'Revelando...' : 'Revelar e copiar',
            icon: Icons.copy_rounded,
            onPressed: _disabled(state) ? null : () => _claim(reveal),
          ),
        ],
      ),
    );
  }

  Widget _slotCard(OpaqueApiKeysState state, OpaqueApiKeySlot slot) {
    final pending = slot.keys.where((key) => key.status == 'pending').toList();
    final busy = state.isSlotBusy(slot.id);
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
          if (busy) ...[
            const SizedBox(height: 8),
            LinearProgressIndicator(
              key: ValueKey('opaque-slot-progress-${slot.id}'),
              minHeight: 2,
            ),
          ],
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
                  onPressed: _disabled(state)
                      ? null
                      : () => _confirmInstallation(slot, key),
                ),
              ),
          const Divider(color: SupabaseColors.border),
          Material(
            type: MaterialType.transparency,
            child: SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              value: slot.automaticRotationEnabled,
              onChanged: _disabled(state) || slot.rotationIntervalDays == null
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
          ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              SecondaryButton(
                label: 'Expiração: '
                    '${_expirationLabel(slot.rotationIntervalDays)}',
                icon: Icons.timer_outlined,
                onPressed:
                    _disabled(state) ? null : () => _editExpirationPolicy(slot),
              ),
              SecondaryButton(
                label: 'Rotacionar agora',
                icon: Icons.refresh_rounded,
                onPressed: _disabled(state) || pending.isNotEmpty
                    ? null
                    : () => _rotate(slot),
              ),
              if (pending.isNotEmpty && state.migration['status'] == 'active')
                SecondaryButton(
                  label: 'Cancelar rotação pendente',
                  icon: Icons.cancel_outlined,
                  onPressed: _disabled(state)
                      ? null
                      : () => _cancelPendingRotation(slot),
                ),
              DangerButton(
                label: 'Revogar slot',
                icon: Icons.block_rounded,
                onPressed: _disabled(state) ? null : () => _disable(slot),
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

class _ClaimedOpaqueApiKeyDialog extends StatefulWidget {
  const _ClaimedOpaqueApiKeyDialog({
    required this.secret,
    required this.reveal,
    required this.initiallyCopied,
    required this.initialClipboardError,
  });

  final String secret;
  final OpaqueApiKeyReveal reveal;
  final bool initiallyCopied;
  final String? initialClipboardError;

  @override
  State<_ClaimedOpaqueApiKeyDialog> createState() =>
      _ClaimedOpaqueApiKeyDialogState();
}

class _ClaimedOpaqueApiKeyDialogState
    extends State<_ClaimedOpaqueApiKeyDialog> {
  late bool _copied = widget.initiallyCopied;
  late String? _clipboardError = widget.initialClipboardError;

  Future<void> _copy() async {
    try {
      await Clipboard.setData(ClipboardData(text: widget.secret));
      if (!mounted) return;
      setState(() {
        _copied = true;
        _clipboardError = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _clipboardError = opaqueApiKeyErrorMessage(error));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: const ValueKey('claimed-opaque-api-key-dialog'),
      backgroundColor: SupabaseColors.bg200,
      title: const Text('API key revelada uma única vez'),
      content: SizedBox(
        width: 560,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'A revelação já foi consumida no servidor. Copie o valor antes '
              'de fechar; ele não poderá ser recuperado novamente.',
              style: TextStyle(color: SupabaseColors.warning),
            ),
            const SizedBox(height: 8),
            Text(
              '${widget.reveal.slotName} · ${widget.reveal.kind}',
              style: const TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 12),
            SelectableText(
              widget.secret,
              key: const ValueKey('claimed-opaque-api-key-plaintext'),
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
            ),
            if (_copied) ...[
              const SizedBox(height: 8),
              const Text(
                'Copiada para a área de transferência.',
                style: TextStyle(color: SupabaseColors.success, fontSize: 11),
              ),
            ],
            if (_clipboardError != null) ...[
              const SizedBox(height: 8),
              Text(
                'Não foi possível copiar automaticamente: $_clipboardError',
                style: const TextStyle(
                  color: SupabaseColors.error,
                  fontSize: 11,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _copy,
          child: Text(_copied ? 'Copiar novamente' : 'Copiar'),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, _copied),
          child: const Text('Fechar'),
        ),
      ],
    );
  }
}

final class _CreateOpaqueSlotDraft {
  const _CreateOpaqueSlotDraft({
    required this.name,
    required this.kind,
    required this.allowedServices,
    required this.automaticRotationEnabled,
    required this.rotationIntervalDays,
  });

  final String name;
  final String kind;
  final List<String> allowedServices;
  final bool automaticRotationEnabled;
  final int? rotationIntervalDays;
}

class _CreateOpaqueSlotDialog extends StatefulWidget {
  const _CreateOpaqueSlotDialog();

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

  void _submit() {
    final name = _name.text;
    if (!RegExp(r'^[a-z][a-z0-9_-]{2,39}$').hasMatch(name)) {
      setState(() => _error = 'Use 3-40 caracteres: a-z, 0-9, _ ou -.');
      return;
    }
    if (_selectedServices.isEmpty) {
      setState(() => _error = 'Selecione ao menos um servico.');
      return;
    }
    Navigator.pop(
      context,
      _CreateOpaqueSlotDraft(
        name: name,
        kind: _kind,
        allowedServices: _selectedServices.toList()..sort(),
        automaticRotationEnabled: _automatic,
        rotationIntervalDays: _interval,
      ),
    );
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
                onChanged: (value) => setState(() => _kind = value!),
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
                        onSelected: (selected) => setState(() {
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
                onChanged: _interval == null
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
                onPressed: _chooseExpirationPolicy,
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
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        TextButton(
          onPressed: _submit,
          child: const Text('Criar e revelar'),
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
