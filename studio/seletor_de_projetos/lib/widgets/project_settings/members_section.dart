import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/project_settings_provider.dart';
import '../../data/project_repository.dart';
import '../../supabase_colors.dart';
import '../section_widget.dart';
import '../error_box.dart';
import '../icon_button_widget.dart';
import '../secondary_button.dart';
import '../danger_button.dart';
import '../../session.dart';
import '../../dialogs/addMemberDialog.dart';
import '../../models/project_member.dart';

class MembersSection extends ConsumerWidget {
  final String projectRef;
  const MembersSection({super.key, required this.projectRef});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final membersAsync = ref.watch(projectMembersProvider(projectRef));

    final myId = Session().myId;
    final myRole =
        membersAsync.value
            ?.firstWhere(
              (m) => m.user_id == myId,
              orElse: () => ProjectMember(user_id: '', role: 'member'),
            )
            .role ??
        'member';

    return SectionWidget(
      title: 'MEMBROS',
      trailing: myRole == 'admin'
          ? SecondaryButton(
              label: 'Adicionar',
              icon: Icons.person_add_rounded,
              onPressed: membersAsync.isLoading
                  ? null
                  : () => _openAddMemberDialog(context, ref),
            )
          : null,
      child: membersAsync.when(
        loading: () => const Center(
          child: Padding(
            padding: EdgeInsets.all(20),
            child: SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: SupabaseColors.brand,
              ),
            ),
          ),
        ),
        error: (err, _) => ErrorBox(
          message: 'Erro ao carregar membros: $err',
          onRetry: () => ref.invalidate(projectMembersProvider(projectRef)),
        ),
        data: (members) {
          if (members.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Text(
                  'Nenhum membro',
                  style: TextStyle(color: SupabaseColors.textMuted),
                ),
              ),
            );
          }
          return Column(
            children: members
                .map(
                  (member) =>
                      _buildMemberItem(context, ref, member, myRole, myId),
                )
                .toList(),
          );
        },
      ),
    );
  }

  Widget _buildMemberItem(
    BuildContext context,
    WidgetRef ref,
    ProjectMember member,
    String myRole,
    String myId,
  ) {
    final isMe = member.user_id == myId;
    final canRemove = myRole == 'admin' && member.role != 'admin' && !isMe;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isMe
            ? SupabaseColors.brand.withValues(alpha: 0.1)
            : SupabaseColors.bg300,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: isMe
              ? SupabaseColors.brand.withValues(alpha: 0.3)
              : SupabaseColors.border,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: member.role == 'admin'
                  ? SupabaseColors.warning.withValues(alpha: 0.2)
                  : SupabaseColors.info.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(
              member.role == 'admin'
                  ? Icons.admin_panel_settings_rounded
                  : Icons.person_rounded,
              color: member.role == 'admin'
                  ? SupabaseColors.warning
                  : SupabaseColors.info,
              size: 18,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isMe
                      ? '${member.displayName ?? 'Você'} (você)'
                      : member.displayName ?? 'Sem nome',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: isMe ? FontWeight.w600 : FontWeight.w500,
                    color: SupabaseColors.textPrimary,
                  ),
                ),
                Text(
                  member.role == 'admin' ? 'Administrador' : 'Membro',
                  style: const TextStyle(
                    fontSize: 11,
                    color: SupabaseColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          if (canRemove)
            IconButtonWidget(
              icon: Icons.remove_circle_outline_rounded,
              tooltip: 'Remover',
              color: SupabaseColors.error,
              onPressed: () => _showRemoveConfirmation(context, ref, member),
            ),
        ],
      ),
    );
  }

  void _showRemoveConfirmation(
    BuildContext context,
    WidgetRef ref,
    ProjectMember member,
  ) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: SupabaseColors.bg200,
        title: const Text(
          'Confirmar Remoção',
          style: TextStyle(color: SupabaseColors.textPrimary),
        ),
        content: Text(
          'Remover ${member.displayName ?? 'este usuário'} do projeto?',
          style: const TextStyle(color: SupabaseColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
          DangerButton(
            label: 'Remover',
            onPressed: () async {
              Navigator.pop(ctx);
              try {
                await ref
                    .read(projectRepositoryProvider)
                    .removeMember(projectRef, member.user_id);
                ref.invalidate(projectMembersProvider(projectRef));
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Membro removido!'),
                      backgroundColor: SupabaseColors.success,
                    ),
                  );
                }
              } catch (e) {
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Erro: $e'),
                      backgroundColor: SupabaseColors.error,
                    ),
                  );
                }
              }
            },
          ),
        ],
      ),
    );
  }

  void _openAddMemberDialog(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (_) => AddMemberDialog(
        loadUsers: () async {
          ref.invalidate(availableUsersProvider(projectRef));
        },
        getUsers: () {
          return ref.read(availableUsersProvider(projectRef)).value ?? [];
        },
        onAdd: (userId, role) async {
          try {
            await ref
                .read(projectRepositoryProvider)
                .addMember(projectRef, userId, role);
            ref.invalidate(projectMembersProvider(projectRef));
            ref.invalidate(availableUsersProvider(projectRef));
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Membro adicionado!'),
                  backgroundColor: SupabaseColors.success,
                ),
              );
            }
          } catch (e) {
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Erro: $e'),
                  backgroundColor: SupabaseColors.error,
                ),
              );
            }
          }
        },
      ),
    );
  }
}
