import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../supabase_colors.dart';
import 'mailer_preview_stub.dart'
    if (dart.library.html) 'mailer_preview_web.dart';

class MailerPreviewData {
  const MailerPreviewData({
    required this.title,
    required this.onClose,
    required this.onRefresh,
    this.html,
    this.error,
    this.loading = false,
    this.allowedOrigins = const [],
  });

  final String title;
  final String? html;
  final String? error;
  final bool loading;
  final List<String> allowedOrigins;
  final VoidCallback onClose;
  final VoidCallback onRefresh;
}

class MailerPreviewLayout extends StatelessWidget {
  const MailerPreviewLayout({super.key, required this.editor, this.preview});
  final Widget editor;
  final MailerPreviewData? preview;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, size) {
        if (preview != null && size.maxWidth >= 1080) {
          return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(child: editor),
            const SizedBox(width: 16),
            Expanded(child: MailerPreviewPanel(data: preview!)),
          ]);
        }
        return Stack(fit: StackFit.expand, children: [
          editor,
          if (preview != null) MailerPreviewPanel(data: preview!),
        ]);
      });
}

class MailerPreviewPanel extends StatefulWidget {
  const MailerPreviewPanel({super.key, required this.data, this.onClose});
  final MailerPreviewData data;
  final VoidCallback? onClose;

  @override
  State<MailerPreviewPanel> createState() => _MailerPreviewPanelState();
}

class _MailerPreviewPanelState extends State<MailerPreviewPanel> {
  bool _mobile = false;

  @override
  Widget build(BuildContext context) {
    final data = widget.data;
    return Material(
      key: const ValueKey('mailer-preview-panel'),
      color: SupabaseColors.bg200,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: SupabaseColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 8, 12),
          child: Row(children: [
            const Icon(Icons.mark_email_read_outlined,
                size: 20, color: SupabaseColors.brand),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Prévia do e-mail',
                        style: TextStyle(
                            fontSize: 17, fontWeight: FontWeight.w600)),
                    Text(data.title,
                        style: const TextStyle(
                            color: SupabaseColors.textSecondary, fontSize: 12)),
                  ]),
            ),
            IconButton(
                tooltip: 'Atualizar prévia',
                onPressed: data.loading ? null : data.onRefresh,
                icon: const Icon(Icons.refresh, size: 20)),
            IconButton(
                tooltip: 'Fechar prévia',
                onPressed: widget.onClose ?? data.onClose,
                icon: const Icon(Icons.close, size: 20)),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
          child: Wrap(spacing: 12, runSpacing: 8, children: [
            if (MediaQuery.textScalerOf(context).scale(12) > 18 ||
                MediaQuery.sizeOf(context).width < 420)
              SizedBox(
                  width: double.infinity,
                  child: DropdownButton<bool>(
                    isExpanded: true,
                    value: _mobile,
                    items: const [
                      DropdownMenuItem(value: false, child: Text('Computador')),
                      DropdownMenuItem(value: true, child: Text('Celular')),
                    ],
                    onChanged: (value) {
                      if (value != null) setState(() => _mobile = value);
                    },
                  ))
            else
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(
                      value: false,
                      icon: Icon(Icons.desktop_windows_outlined, size: 16),
                      label: Text('Computador')),
                  ButtonSegment(
                      value: true,
                      icon: Icon(Icons.phone_android, size: 16),
                      label: Text('Celular')),
                ],
                selected: {_mobile},
                onSelectionChanged: (value) =>
                    setState(() => _mobile = value.single),
              ),
            Text(
              data.loading
                  ? 'Atualizando prévia...'
                  : data.error != null
                      ? 'A prévia não foi atualizada'
                      : 'Prévia com dados de exemplo',
              style: const TextStyle(
                  color: SupabaseColors.textSecondary, fontSize: 12),
            ),
          ]),
        ),
        SizedBox(
            height: 2,
            child: data.loading ? const LinearProgressIndicator() : null),
        if (data.error != null)
          Padding(
              padding: const EdgeInsets.all(16),
              child: Text(data.error!,
                  style: const TextStyle(color: SupabaseColors.error))),
        Expanded(
          child: ColoredBox(
            color: const Color(0xffe9edf2),
            child: data.html == null
                ? Center(
                    child: Text(
                        data.loading
                            ? 'Preparando prévia...'
                            : 'Ajuste o HTML para visualizar o e-mail.',
                        style: const TextStyle(color: Color(0xff4b5563))))
                : LayoutBuilder(builder: (context, size) {
                    final width = _mobile
                        ? math.min(375.0, size.maxWidth)
                        : math.max(600.0, size.maxWidth);
                    return Align(
                      alignment: Alignment.topCenter,
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: SizedBox(
                          width: width,
                          height: size.maxHeight,
                          child: MailerPreview(
                              html: data.html!,
                              allowedOrigins: data.allowedOrigins),
                        ),
                      ),
                    );
                  }),
          ),
        ),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          child: Text(
              'Atualiza enquanto você edita. Visualizar não salva nem publica alterações.',
              style:
                  TextStyle(color: SupabaseColors.textSecondary, fontSize: 12)),
        ),
      ]),
    );
  }
}
