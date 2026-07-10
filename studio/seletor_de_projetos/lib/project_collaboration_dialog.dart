import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'data/project_repository.dart';
import 'models/project_collaboration.dart';
import 'providers/project_collaboration_provider.dart';
import 'session.dart';
import 'supabase_colors.dart';
import 'widgets/supabase_button.dart';

class ProjectCollaborationDialog extends ConsumerStatefulWidget {
  const ProjectCollaborationDialog({super.key, required this.projectRef});

  final String projectRef;

  @override
  ConsumerState<ProjectCollaborationDialog> createState() =>
      _ProjectCollaborationDialogState();
}

class _ProjectCollaborationDialogState
    extends ConsumerState<ProjectCollaborationDialog> {
  final _noteController = TextEditingController();
  final _tagController = TextEditingController();
  final _hintController = TextEditingController();
  final _threadController = TextEditingController();
  static const _tagPalette = [
    '#3ECF8E',
    '#3B82F6',
    '#A78BFA',
    '#F59E0B',
    '#EF4444',
    '#14B8A6',
    '#64748B',
  ];
  String _visibility = 'private';
  String _tagColor = _tagPalette.first;
  String? _selectedHintTargetUserId;
  bool _creatingTag = false;
  bool _savingNote = false;
  bool _savingTag = false;
  bool _savingHint = false;
  bool _sendingThreadMessage = false;

  @override
  void dispose() {
    _noteController.dispose();
    _tagController.dispose();
    _hintController.dispose();
    _threadController.dispose();
    super.dispose();
  }

  Future<void> _saveNote() async {
    final body = _noteController.text.trim();
    if (body.isEmpty) return;

    setState(() => _savingNote = true);
    try {
      await ref.read(projectRepositoryProvider).createProjectNote(
            widget.projectRef,
            body: body,
            visibility: _visibility,
          );
      _noteController.clear();
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    } finally {
      if (mounted) setState(() => _savingNote = false);
    }
  }

  Future<void> _toggleTag(ProjectTag tag) async {
    final repo = ref.read(projectRepositoryProvider);
    if (tag.assigned) {
      try {
        await repo.removeProjectTag(widget.projectRef, tag.id);
      } catch (err) {
        _showError(err.toString());
        return;
      }
    } else {
      try {
        await repo.assignProjectTag(widget.projectRef, tagId: tag.id);
      } catch (err) {
        _showError(err.toString());
        return;
      }
    }
    ref.invalidate(projectCollaborationProvider(widget.projectRef));
  }

  Future<void> _createTag() async {
    final name = _tagController.text.trim();
    if (name.isEmpty) return;

    setState(() => _savingTag = true);
    try {
      await ref.read(projectRepositoryProvider).assignProjectTag(
            widget.projectRef,
            name: name,
            color: _tagColor,
          );
      _tagController.clear();
      setState(() => _creatingTag = false);
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    } finally {
      if (mounted) setState(() => _savingTag = false);
    }
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: SupabaseColors.error,
      ),
    );
  }

  Future<void> _deleteNote(ProjectNote note) async {
    try {
      await ref
          .read(projectRepositoryProvider)
          .deleteProjectNote(widget.projectRef, note.id);
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    }
  }

  Future<void> _createHint(ProjectCollaboration data) async {
    final body = _hintController.text.trim();
    final targetUserId = _selectedHintTargetUserId ??
        (data.members.isEmpty ? null : data.members.first.id);
    if (body.isEmpty || targetUserId == null) return;

    setState(() => _savingHint = true);
    try {
      await ref.read(projectRepositoryProvider).createProjectHint(
            widget.projectRef,
            targetUserId: targetUserId,
            body: body,
          );
      _hintController.clear();
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    } finally {
      if (mounted) setState(() => _savingHint = false);
    }
  }

  Future<void> _toggleHintStatus(ProjectHint hint) async {
    final nextStatus = hint.isOpen ? 'resolved' : 'open';
    try {
      await ref.read(projectRepositoryProvider).updateProjectHintStatus(
            widget.projectRef,
            hint.id,
            nextStatus,
          );
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    }
  }

  Future<void> _sendThreadMessage() async {
    final body = _threadController.text.trim();
    if (body.isEmpty) return;

    setState(() => _sendingThreadMessage = true);
    try {
      await ref.read(projectRepositoryProvider).createProjectThreadMessage(
            widget.projectRef,
            body: body,
          );
      _threadController.clear();
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    } finally {
      if (mounted) setState(() => _sendingThreadMessage = false);
    }
  }

  Future<void> _toggleNotification(ProjectNotification notification) async {
    try {
      await ref
          .read(projectRepositoryProvider)
          .updateProjectNotificationReadState(
            widget.projectRef,
            notification.id,
            read: !notification.isRead,
          );
      ref.invalidate(projectCollaborationProvider(widget.projectRef));
    } catch (err) {
      _showError(err.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final collaboration = ref.watch(
      projectCollaborationProvider(widget.projectRef),
    );

    return Dialog(
      backgroundColor: SupabaseColors.bg200,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: SupabaseColors.border),
      ),
      child: SizedBox(
        width: 720,
        height: 760,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: collaboration.when(
            loading: () => const SizedBox(
              height: 260,
              child: Center(
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: SupabaseColors.brand,
                ),
              ),
            ),
            error: (err, _) => _buildError(err.toString()),
            data: (data) => _buildContent(data),
          ),
        ),
      ),
    );
  }

  Widget _buildContent(ProjectCollaboration data) {
    return DefaultTabController(
      length: 4,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.edit_note_rounded,
                size: 22,
                color: SupabaseColors.brand,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.projectRef,
                  style: const TextStyle(
                    color: SupabaseColors.textPrimary,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              IconBtn(
                icon: Icons.close_rounded,
                tooltip: 'Fechar',
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          const SizedBox(height: 18),
          _buildTagSection(data),
          const SizedBox(height: 16),
          const TabBar(
            indicatorColor: SupabaseColors.brand,
            labelColor: SupabaseColors.textPrimary,
            unselectedLabelColor: SupabaseColors.textMuted,
            tabs: [
              Tab(icon: Icon(Icons.notes_rounded), text: 'Anotações'),
              Tab(icon: Icon(Icons.lightbulb_outline_rounded), text: 'Hints'),
              Tab(icon: Icon(Icons.forum_outlined), text: 'Thread'),
              Tab(
                icon: Icon(Icons.notifications_outlined),
                text: 'Notificacoes',
              ),
            ],
          ),
          const SizedBox(height: 12),
          Expanded(
            child: TabBarView(
              children: [
                _buildNotesTab(data),
                _buildHintsTab(data),
                _buildThreadTab(data),
                _buildNotificationsTab(data),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTagSection(ProjectCollaboration data) {
    final tags = data.availableTags;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'TAGS',
              style: TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1,
              ),
            ),
            const Spacer(),
            if (Session().isSysAdmin)
              TextButton.icon(
                onPressed: () => setState(() => _creatingTag = !_creatingTag),
                icon: Icon(
                  _creatingTag ? Icons.close_rounded : Icons.add_rounded,
                  size: 16,
                ),
                label: Text(_creatingTag ? 'Cancelar' : 'Nova tag'),
              ),
          ],
        ),
        const SizedBox(height: 10),
        if (_creatingTag) ...[
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SupabaseColors.bg300.withValues(alpha: 0.65),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: SupabaseColors.border),
            ),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _tagController,
                        maxLength: 40,
                        style: const TextStyle(
                          color: SupabaseColors.textPrimary,
                        ),
                        decoration: const InputDecoration(
                          counterText: '',
                          hintText: 'Nome da tag',
                          prefixIcon: Icon(Icons.sell_outlined, size: 18),
                        ),
                        onSubmitted: (_) => _savingTag ? null : _createTag(),
                      ),
                    ),
                    const SizedBox(width: 10),
                    SupabaseButton(
                      onPressed: _savingTag ? null : _createTag,
                      icon: Icons.add_rounded,
                      label: 'Criar',
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _tagPalette.map((hex) {
                      final selected = _tagColor == hex;
                      final color = _parseTagColor(hex);
                      return Tooltip(
                        message: hex,
                        child: InkWell(
                          onTap: () => setState(() => _tagColor = hex),
                          borderRadius: BorderRadius.circular(999),
                          child: Container(
                            width: 26,
                            height: 26,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: color,
                              border: Border.all(
                                color: selected
                                    ? SupabaseColors.textPrimary
                                    : SupabaseColors.border,
                                width: selected ? 2 : 1,
                              ),
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 128),
          child: SingleChildScrollView(
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: tags.map((tag) {
                final color = _parseTagColor(tag.color);
                return FilterChip(
                  selected: tag.assigned,
                  label: Text(tag.name),
                  avatar: CircleAvatar(backgroundColor: color, radius: 5),
                  onSelected: (_) => _toggleTag(tag),
                  backgroundColor: SupabaseColors.bg300,
                  selectedColor: color.withValues(alpha: 0.16),
                  checkmarkColor: color,
                  side: BorderSide(
                    color: tag.assigned ? color : SupabaseColors.border,
                  ),
                  labelStyle: const TextStyle(
                    color: SupabaseColors.textPrimary,
                    fontSize: 12,
                  ),
                );
              }).toList(),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildNotesTab(ProjectCollaboration data) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildNoteForm(),
          const SizedBox(height: 18),
          _buildNotes(data.notes),
        ],
      ),
    );
  }

  Widget _buildHintsTab(ProjectCollaboration data) {
    final selectedTarget =
        data.members.any((m) => m.id == _selectedHintTargetUserId)
            ? _selectedHintTargetUserId
            : (data.members.isEmpty ? null : data.members.first.id);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String>(
                initialValue: selectedTarget,
                dropdownColor: SupabaseColors.bg300,
                decoration: const InputDecoration(
                  labelText: 'Direcionado para',
                  isDense: true,
                ),
                items: data.members
                    .map(
                      (member) => DropdownMenuItem<String>(
                        value: member.id,
                        child: Text(
                          member.label,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    )
                    .toList(),
                onChanged: (value) =>
                    setState(() => _selectedHintTargetUserId = value),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _hintController,
                maxLines: 2,
                maxLength: 2000,
                style: const TextStyle(color: SupabaseColors.textPrimary),
                decoration: const InputDecoration(
                  hintText: 'Escreva um hint operacional',
                  counterText: '',
                ),
                onSubmitted: (_) => _savingHint ? null : _createHint(data),
              ),
            ),
            const SizedBox(width: 12),
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: SupabaseButton(
                onPressed: _savingHint || data.members.isEmpty
                    ? null
                    : () => _createHint(data),
                icon: Icons.add_task_rounded,
                label: 'Criar',
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: data.hints.isEmpty
              ? const Center(
                  child: Text(
                    'Nenhum hint ainda.',
                    style: TextStyle(color: SupabaseColors.textMuted),
                  ),
                )
              : ListView.separated(
                  itemCount: data.hints.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, index) => _buildHintItem(data.hints[index]),
                ),
        ),
      ],
    );
  }

  Widget _buildHintItem(ProjectHint hint) {
    final statusColor =
        hint.isOpen ? SupabaseColors.warning : SupabaseColors.brand;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SupabaseColors.bg300.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: SupabaseColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: statusColor),
                ),
                child: Text(
                  hint.isOpen ? 'Open' : 'Resolved',
                  style: TextStyle(
                    color: statusColor,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '${hint.targetName} • ${hint.authorName} • ${_formatDate(hint.createdAt)}',
                  style: const TextStyle(
                    color: SupabaseColors.textSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (hint.canUpdate)
                TextButton.icon(
                  onPressed: () => _toggleHintStatus(hint),
                  icon: Icon(
                    hint.isOpen
                        ? Icons.check_circle_outline_rounded
                        : Icons.refresh_rounded,
                    size: 16,
                  ),
                  label: Text(hint.isOpen ? 'Resolver' : 'Reabrir'),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            hint.body,
            style: const TextStyle(
              color: SupabaseColors.textPrimary,
              fontSize: 13,
              height: 1.35,
            ),
          ),
          if (!hint.isOpen && hint.resolvedAt != null) ...[
            const SizedBox(height: 8),
            Text(
              'Resolvido por ${hint.resolvedByName ?? 'operador'} em ${_formatDate(hint.resolvedAt!)}',
              style: const TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 12,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildThreadTab(ProjectCollaboration data) {
    return Column(
      children: [
        Expanded(
          child: data.threadMessages.isEmpty
              ? const Center(
                  child: Text(
                    'Nenhuma mensagem ainda.',
                    style: TextStyle(color: SupabaseColors.textMuted),
                  ),
                )
              : ListView.separated(
                  itemCount: data.threadMessages.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, index) =>
                      _buildThreadMessage(data.threadMessages[index]),
                ),
        ),
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: _threadController,
                minLines: 1,
                maxLines: 4,
                maxLength: 4000,
                style: const TextStyle(color: SupabaseColors.textPrimary),
                decoration: const InputDecoration(
                  hintText: 'Mensagem da thread do projeto',
                  counterText: '',
                ),
                onSubmitted: (_) =>
                    _sendingThreadMessage ? null : _sendThreadMessage(),
              ),
            ),
            const SizedBox(width: 12),
            SupabaseButton(
              onPressed: _sendingThreadMessage ? null : _sendThreadMessage,
              icon: Icons.send_rounded,
              label: 'Enviar',
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildThreadMessage(ProjectThreadMessage message) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: SupabaseColors.bg300.withValues(alpha: 0.45),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: SupabaseColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${message.authorName} • ${_formatDate(message.createdAt)}',
              style: const TextStyle(
                color: SupabaseColors.textSecondary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              message.body,
              style: const TextStyle(
                color: SupabaseColors.textPrimary,
                fontSize: 13,
                height: 1.35,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNotificationsTab(ProjectCollaboration data) {
    if (data.notifications.isEmpty) {
      return const Center(
        child: Text(
          'Nenhuma notificacao ainda.',
          style: TextStyle(color: SupabaseColors.textMuted),
        ),
      );
    }

    return ListView.separated(
      itemCount: data.notifications.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (_, index) {
        final notification = data.notifications[index];
        final renameFrom = notification.payload['old_name']?.toString();
        final renameTo = notification.payload['new_name']?.toString();
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: notification.isRead
                ? SupabaseColors.bg300.withValues(alpha: 0.35)
                : SupabaseColors.brand.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: notification.isRead
                  ? SupabaseColors.border
                  : SupabaseColors.brand,
            ),
          ),
          child: Row(
            children: [
              Icon(
                notification.isRead
                    ? Icons.notifications_none_rounded
                    : Icons.notifications_active_outlined,
                color: notification.isRead
                    ? SupabaseColors.textMuted
                    : SupabaseColors.brand,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      notification.label,
                      style: const TextStyle(
                        color: SupabaseColors.textPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      renameFrom != null && renameTo != null
                          ? '$renameFrom -> $renameTo • ${notification.actorName}'
                          : '${notification.actorName} • ${_formatDate(notification.createdAt)}',
                      style: const TextStyle(
                        color: SupabaseColors.textMuted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: () => _toggleNotification(notification),
                child: Text(notification.isRead ? 'Marcar nao lida' : 'Lida'),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildNoteForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'ANOTAÇÃO',
              style: TextStyle(
                color: SupabaseColors.textMuted,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1,
              ),
            ),
            const Spacer(),
            SizedBox(
              width: 150,
              child: DropdownButtonFormField<String>(
                initialValue: _visibility,
                dropdownColor: SupabaseColors.bg300,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 8,
                  ),
                ),
                items: const [
                  DropdownMenuItem(value: 'private', child: Text('Privada')),
                  DropdownMenuItem(value: 'public', child: Text('Pública')),
                ],
                onChanged: (value) {
                  if (value != null) setState(() => _visibility = value);
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _noteController,
          minLines: 3,
          maxLines: 5,
          maxLength: 4000,
          style: const TextStyle(color: SupabaseColors.textPrimary),
          decoration: const InputDecoration(
            hintText: 'Escreva uma observação para este projeto',
            alignLabelWithHint: true,
          ),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: SupabaseButton(
            onPressed: _savingNote ? null : _saveNote,
            icon: Icons.save_outlined,
            label: 'Salvar',
          ),
        ),
      ],
    );
  }

  Widget _buildNotes(List<ProjectNote> notes) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 300),
      child: notes.isEmpty
          ? const Padding(
              padding: EdgeInsets.symmetric(vertical: 18),
              child: Text(
                'Nenhuma anotação ainda.',
                style: TextStyle(color: SupabaseColors.textMuted),
              ),
            )
          : ListView.separated(
              shrinkWrap: true,
              itemCount: notes.length,
              separatorBuilder: (_, __) =>
                  const Divider(color: SupabaseColors.border),
              itemBuilder: (_, index) {
                final note = notes[index];
                final isPublic = note.visibility == 'public';
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: SupabaseColors.bg300.withValues(alpha: 0.45),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: SupabaseColors.border),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 7,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: isPublic
                                    ? SupabaseColors.brand.withValues(
                                        alpha: 0.12,
                                      )
                                    : SupabaseColors.surface300,
                                borderRadius: BorderRadius.circular(999),
                                border: Border.all(
                                  color: isPublic
                                      ? SupabaseColors.brand
                                      : SupabaseColors.border,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    isPublic
                                        ? Icons.groups_rounded
                                        : Icons.lock_outline_rounded,
                                    size: 13,
                                    color: isPublic
                                        ? SupabaseColors.brand
                                        : SupabaseColors.textMuted,
                                  ),
                                  const SizedBox(width: 5),
                                  Text(
                                    isPublic ? 'Pública' : 'Privada',
                                    style: TextStyle(
                                      color: isPublic
                                          ? SupabaseColors.brand
                                          : SupabaseColors.textSecondary,
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                '${note.authorName} • ${_formatDate(note.createdAt)}',
                                style: const TextStyle(
                                  color: SupabaseColors.textSecondary,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            if (note.canDelete)
                              IconBtn(
                                icon: Icons.delete_outline_rounded,
                                tooltip: 'Excluir anotação',
                                color: SupabaseColors.error,
                                onPressed: () => _deleteNote(note),
                              ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            note.body,
                            style: const TextStyle(
                              color: SupabaseColors.textPrimary,
                              fontSize: 13,
                              height: 1.35,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }

  Widget _buildError(String message) {
    return SizedBox(
      height: 220,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            Icons.error_outline_rounded,
            color: SupabaseColors.error,
            size: 30,
          ),
          const SizedBox(height: 12),
          Text(
            message,
            style: const TextStyle(color: SupabaseColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 18),
          SupabaseButton(
            onPressed: () =>
                ref.invalidate(projectCollaborationProvider(widget.projectRef)),
            icon: Icons.refresh_rounded,
            label: 'Tentar de novo',
          ),
        ],
      ),
    );
  }

  String _formatDate(DateTime value) {
    final local = value.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(local.day)}/${two(local.month)}/${local.year} ${two(local.hour)}:${two(local.minute)}';
  }

  Color _parseTagColor(String hex) {
    final clean = hex.replaceFirst('#', '');
    if (clean.length != 6) return SupabaseColors.brand;
    try {
      return Color(int.parse('FF$clean', radix: 16));
    } on FormatException {
      return SupabaseColors.brand;
    }
  }
}
