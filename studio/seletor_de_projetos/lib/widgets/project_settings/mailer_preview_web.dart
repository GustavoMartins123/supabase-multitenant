// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;
import 'package:flutter/material.dart';

class MailerPreview extends StatefulWidget {
  const MailerPreview({super.key, required this.html});
  final String html;
  @override
  State<MailerPreview> createState() => _MailerPreviewState();
}

class _MailerPreviewState extends State<MailerPreview> {
  static int _sequence = 0;
  late final String _viewType;
  late final html.IFrameElement _frame;

  void _update() {
    _frame.srcdoc = '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        'style-src &#39;unsafe-inline&#39;; img-src data:; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
        '</head><body>${widget.html}</body></html>';
  }

  @override
  void initState() {
    super.initState();
    _viewType = 'mailer-preview-${_sequence++}';
    _frame = html.IFrameElement()
      ..setAttribute('sandbox', '')
      ..setAttribute('referrerpolicy', 'no-referrer')
      ..title = 'Prévia do e-mail'
      ..style.border = '0'
      ..style.width = '100%'
      ..style.height = '100%'
      ..style.backgroundColor = 'white';
    _update();
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (_) => _frame);
  }

  @override
  void didUpdateWidget(covariant MailerPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.html != widget.html) _update();
  }

  @override
  void dispose() {
    _frame.remove();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => HtmlElementView(viewType: _viewType);
}
