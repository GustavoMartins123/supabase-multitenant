
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/project_repository.dart';
import '../project_settings_dialog.dart';
import '../supabase_colors.dart';
import 'supabase_button.dart';

class ProjectCard extends ConsumerStatefulWidget {
  const ProjectCard({
    super.key,
    required this.refKey,
    required this.anonKey,
    required this.configToken,
    required this.onTap,
    required this.onDeleted,
    required this.onDuplicate,
    required this.onToggleFavorite,
    required this.isFavorite,
    this.serverDomain,
    this.isLoading = false,
  });

  final String refKey;
  final String anonKey;
  final String configToken;
  final String? serverDomain;
  final VoidCallback onTap;
  final VoidCallback onDeleted;
  final VoidCallback onDuplicate;
  final VoidCallback onToggleFavorite;
  final bool isLoading;
  final bool isFavorite;

  @override
  ConsumerState<ProjectCard> createState() => _ProjectCardState();
}

class _ProjectCardState extends ConsumerState<ProjectCard>
    with TickerProviderStateMixin {
  bool _hover = false;
  bool _keyVisible = false;

  late final Future<String?> _statusFuture;

  @override
  void initState() {
    super.initState();
    if (!widget.isLoading) {
      _statusFuture = ref
          .read(projectRepositoryProvider)
          .fetchProjectStatus(widget.refKey);
    }
  }

  Future<void> _openSettings() async {
    final deleted = await showDialog<String>(
      context: context,
      builder: (_) => ProjectSettingsDialog(
        ref: widget.refKey,
        anonKey: widget.anonKey,
        configToken: widget.configToken,
      ),
    );

    if (deleted == widget.refKey) {
      widget.onDeleted();
    }
  }

  String get _projectUrl {
    if (widget.serverDomain == null || widget.serverDomain!.isEmpty) {
      return widget.refKey;
    }
    return '${widget.serverDomain}/${widget.refKey}';
  }

  @override
  Widget build(BuildContext ctx) {
    if (widget.isLoading) {
      return _buildLoadingCard();
    }

    return FutureBuilder<String?>(
      future: _statusFuture,
      builder: (context, snapshot) {
        final isRunning = snapshot.data == 'running';
        final statusLoading = snapshot.connectionState != ConnectionState.done;

        return MouseRegion(
          onEnter: (_) => setState(() => _hover = true),
          onExit: (_) => setState(() => _hover = false),
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            onTap: widget.onTap,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeOut,
              decoration: BoxDecoration(
                color: _hover
                    ? SupabaseColors.surface200
                    : SupabaseColors.surface100,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: _hover
                      ? SupabaseColors.borderHover
                      : SupabaseColors.border,
                  width: 1,
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 48,
                          height: 48,
                          decoration: BoxDecoration(
                            color: SupabaseColors.bg300,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.storage_rounded,
                            color: SupabaseColors.brand,
                            size: 24,
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Flexible(
                                    child: Text(
                                      widget.refKey,
                                      style: const TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                        color: SupabaseColors.textPrimary,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Container(
                                    width: 8,
                                    height: 8,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: statusLoading
                                          ? SupabaseColors.textMuted
                                          : (isRunning
                                                ? SupabaseColors.brand
                                                : SupabaseColors.error),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      _projectUrl,
                                      style: const TextStyle(
                                        fontSize: 13,
                                        color: SupabaseColors.textMuted,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  const SizedBox(width: 4),
                                  IconBtn(
                                    icon: Icons.link_rounded,
                                    tooltip: 'Copiar URL',
                                    onPressed: () {
                                      Clipboard.setData(
                                        ClipboardData(text: _projectUrl),
                                      );
                                      ScaffoldMessenger.of(
                                        context,
                                      ).showSnackBar(
                                        const SnackBar(
                                          content: Text('URL copiada!'),
                                          backgroundColor:
                                              SupabaseColors.success,
                                        ),
                                      );
                                    },
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconBtn(
                              icon: widget.isFavorite
                                  ? Icons.star_rounded
                                  : Icons.star_border_rounded,
                              color: widget.isFavorite
                                  ? SupabaseColors.favorite
                                  : SupabaseColors.textSecondary,
                              tooltip: widget.isFavorite
                                  ? 'Remover dos favoritos'
                                  : 'Adicionar aos favoritos',
                              onPressed: widget.onToggleFavorite,
                            ),
                            PopupMenuButton<String>(
                              icon: const Icon(
                                Icons.more_vert_rounded,
                                color: SupabaseColors.textSecondary,
                                size: 20,
                              ),
                              color: SupabaseColors.bg300,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                                side: const BorderSide(
                                  color: SupabaseColors.border,
                                ),
                              ),
                              offset: const Offset(0, 40),
                              onSelected: (val) {
                                if (val == 'settings') _openSettings();
                                if (val == 'duplicate') widget.onDuplicate();
                              },
                              itemBuilder: (ctx) => [
                                _buildMenuItem(
                                  'settings',
                                  Icons.settings_outlined,
                                  'Configurações do Projeto',
                                ),
                                _buildMenuItem(
                                  'duplicate',
                                  Icons.copy_outlined,
                                  'Duplicar projeto e dados',
                                ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                    const Spacer(),
                    const Text(
                      'CHAVE ANÔNIMA',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: SupabaseColors.textMuted,
                        letterSpacing: 1.0,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: SupabaseColors.bg300.withValues(alpha: 0.5),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: SupabaseColors.border),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              _keyVisible
                                  ? widget.anonKey
                                  : '••••••••••••••••••••••••••••••',
                              style: const TextStyle(
                                fontSize: 13,
                                color: SupabaseColors.textSecondary,
                                fontFamily: 'monospace',
                                letterSpacing: 2,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          IconBtn(
                            icon: _keyVisible
                                ? Icons.visibility_off_outlined
                                : Icons.visibility_outlined,
                            tooltip: _keyVisible
                                ? 'Esconder chave'
                                : 'Mostrar chave',
                            onPressed: () =>
                                setState(() => _keyVisible = !_keyVisible),
                          ),
                          IconBtn(
                            icon: Icons.copy_outlined,
                            tooltip: 'Copiar chave',
                            onPressed: () {
                              Clipboard.setData(
                                ClipboardData(text: widget.anonKey),
                              );
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Chave copiada!'),
                                  backgroundColor: SupabaseColors.success,
                                ),
                              );
                            },
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  PopupMenuItem<String> _buildMenuItem(
    String value,
    IconData icon,
    String label,
  ) {
    return PopupMenuItem<String>(
      value: value,
      child: Row(
        children: [
          Icon(icon, size: 18, color: SupabaseColors.textSecondary),
          const SizedBox(width: 12),
          Text(
            label,
            style: const TextStyle(
              color: SupabaseColors.textPrimary,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusIndicator(bool isRunning, bool isLoading) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: isLoading
            ? SupabaseColors.surface200
            : (isRunning
                  ? SupabaseColors.success.withValues(alpha: 0.1)
                  : SupabaseColors.error.withValues(alpha: 0.1)),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isLoading
              ? SupabaseColors.border
              : (isRunning
                    ? SupabaseColors.success.withValues(alpha: 0.2)
                    : SupabaseColors.error.withValues(alpha: 0.2)),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isLoading
                  ? SupabaseColors.textMuted
                  : (isRunning ? SupabaseColors.success : SupabaseColors.error),
            ),
          ),
          const SizedBox(width: 6),
          Text(
            isLoading ? 'Verificando...' : (isRunning ? 'Rodando' : 'Parado'),
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: isLoading
                  ? SupabaseColors.textMuted
                  : (isRunning ? SupabaseColors.success : SupabaseColors.error),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingCard() {
    return Container(
      decoration: BoxDecoration(
        color: SupabaseColors.surface100,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: SupabaseColors.border),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _buildShimmer(40, 40, borderRadius: 8),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildShimmer(120, 16),
                    const SizedBox(height: 8),
                    _buildShimmer(200, 12),
                  ],
                ),
              ),
            ],
          ),
          const Spacer(),
          const SizedBox(height: 16),
          _buildShimmer(double.infinity, 32),
        ],
      ),
    );
  }

  Widget _buildShimmer(double width, double height, {double borderRadius = 4}) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.3, end: 0.7),
      duration: const Duration(seconds: 1),
      builder: (context, val, child) {
        return Container(
          width: width,
          height: height,
          decoration: BoxDecoration(
            color: SupabaseColors.surface200.withValues(alpha: val),
            borderRadius: BorderRadius.circular(borderRadius),
          ),
        );
      },
      onEnd: () {},
    );
  }
}
