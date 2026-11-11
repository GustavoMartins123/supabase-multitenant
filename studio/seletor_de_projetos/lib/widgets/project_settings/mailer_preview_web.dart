// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;
import 'dart:convert';
import 'package:flutter/material.dart';

html.IFrameElement createMailerPreviewFrame() => html.IFrameElement()
  ..setAttribute('sandbox', '')
  ..setAttribute('referrerpolicy', 'no-referrer')
  ..title = 'Prévia do e-mail'
  ..style.border = '0'
  ..style.width = '100%'
  ..style.height = '100%'
  ..style.backgroundColor = 'white';

void updateMailerPreviewFrame(
    html.IFrameElement frame, String body, List<String> allowedOrigins) {
  final approved = allowedOrigins.where((origin) {
    final uri = Uri.tryParse(origin);
    return uri != null &&
        uri.scheme == 'https' &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        uri.path.isEmpty &&
        !uri.hasQuery &&
        !uri.hasFragment &&
        !RegExp(r'[\s;]').hasMatch(origin);
  }).join(' ');
  final policy = const HtmlEscape(HtmlEscapeMode.attribute).convert(
      "default-src 'none'; style-src 'unsafe-inline'; img-src data: $approved; "
      "base-uri 'none'; form-action 'none'; connect-src 'none';");
  // Sandbox still allows links to navigate this frame. Keep the email inert
  // so previewing it preserves the layout without activating its controls.
  frame.srcdoc = '<!doctype html><html><head><meta charset="utf-8">'
      '<meta http-equiv="Content-Security-Policy" content="$policy">'
      '</head><body inert style="margin:0">$body</body></html>';
}

class MailerPreview extends StatefulWidget {
  const MailerPreview(
      {super.key, required this.html, this.allowedOrigins = const []});
  final String html;
  final List<String> allowedOrigins;
  @override
  State<MailerPreview> createState() => _MailerPreviewState();
}

class _MailerPreviewState extends State<MailerPreview> {
  static int _sequence = 0;
  late final String _viewType;
  late final html.IFrameElement _frame;

  void _update() {
    updateMailerPreviewFrame(_frame, widget.html, widget.allowedOrigins);
  }

  @override
  void initState() {
    super.initState();
    _viewType = 'mailer-preview-${_sequence++}';
    _frame = createMailerPreviewFrame();
    _update();
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (_) => _frame);
  }

  @override
  void didUpdateWidget(covariant MailerPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.html != widget.html ||
        oldWidget.allowedOrigins != widget.allowedOrigins) {
      _update();
    }
  }

  @override
  void dispose() {
    _frame.remove();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Native iframe surfaces can intercept clicks on Flutter dialogs above
    // them. Only the current route may capture events inside the preview.
    _frame.style.pointerEvents =
        (ModalRoute.isCurrentOf(context) ?? true) ? 'auto' : 'none';
    return HtmlElementView(viewType: _viewType);
  }
}
