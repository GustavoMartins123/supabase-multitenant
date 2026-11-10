@TestOn('browser')
library;

// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/widgets/project_settings/mailer_preview_web.dart';

void main() {
  test('HTML preview loads in a real isolated browser frame and can be updated',
      () async {
    final frame = createMailerPreviewFrame();
    frame.style.width = '600px';
    frame.style.height = '500px';
    addTearDown(frame.remove);
    final loaded = frame.onLoad.first;
    updateMailerPreviewFrame(
        frame, '<h1>Seu código de acesso</h1><strong>123456</strong>', [
      'https://assets.example.com',
      'https://bad.example.com; script-src *'
    ]);
    html.document.body!.append(frame);
    await loaded.timeout(const Duration(seconds: 5));
    expect(frame.srcdoc, contains('<strong>123456</strong>'));
    expect(frame.attributes['sandbox'], '');
    expect(frame.attributes['referrerpolicy'], 'no-referrer');
    expect(frame.srcdoc, contains('https://assets.example.com'));
    expect(frame.srcdoc, isNot(contains('bad.example.com')));
    expect(frame.getBoundingClientRect().width, 600);
    final updated = frame.onLoad.first;
    updateMailerPreviewFrame(
        frame, '<h1>Atualizado</h1><strong>654321</strong>', []);
    await updated.timeout(const Duration(seconds: 5));
    expect(frame.srcdoc, contains('<strong>654321</strong>'));
    expect(frame.srcdoc, isNot(contains('123456')));
  });
}
