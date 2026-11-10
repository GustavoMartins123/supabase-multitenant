import 'package:flutter/material.dart';

class MailerPreview extends StatelessWidget {
  const MailerPreview(
      {super.key, required this.html, this.allowedOrigins = const []});
  final String html;
  final List<String> allowedOrigins;
  @override
  Widget build(BuildContext context) =>
      SingleChildScrollView(child: SelectableText(html));
}
