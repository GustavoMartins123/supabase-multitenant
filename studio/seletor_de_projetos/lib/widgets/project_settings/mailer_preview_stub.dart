import 'package:flutter/material.dart';

class MailerPreview extends StatelessWidget {
  const MailerPreview({super.key, required this.html});
  final String html;
  @override
  Widget build(BuildContext context) =>
      SingleChildScrollView(child: SelectableText(html));
}
