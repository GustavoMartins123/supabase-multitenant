@TestOn('browser')
library;

// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:js_interop';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/widgets/project_settings/mailer_preview_web.dart';

@JS('document.querySelector')
external _PreviewFrame _inspectFrame(String selector);

extension type _PreviewFrame(JSObject _) implements JSObject {
  external _PreviewDocument get contentDocument;
}

extension type _PreviewDocument(JSObject _) implements JSObject {
  external _PreviewWindow get defaultView;
  external _PreviewElement get documentElement;
  external _PreviewElement querySelector(String selector);
}

extension type _PreviewElement(JSObject _) implements JSObject {
  external String get textContent;
  external void focus();
  external bool matches(String selector);
  external double get scrollTop;
  external set scrollTop(double value);
}

extension type _PreviewWindow(JSObject _) implements JSObject {
  external _PreviewStyle getComputedStyle(_PreviewElement element);
}

extension type _PreviewStyle(JSObject _) implements JSObject {
  external String get color;
}

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

  test(
      'preview preserves styling and scrolling while controls cannot gain focus',
      () async {
    final frame = createMailerPreviewFrame()
      // Test-only access to inspect native focus and layout inside the frame.
      // Production keeps the opaque origin with sandbox="".
      ..setAttribute('sandbox', 'allow-same-origin')
      ..id = 'inert-preview-test'
      ..style.width = '600px'
      ..style.height = '200px';
    addTearDown(frame.remove);
    final loaded = frame.onLoad.first;
    updateMailerPreviewFrame(frame, '''
      <style>
        body { min-height: 2000px; }
        a { display: block; color: rgb(12, 34, 56); }
      </style>
      <a id="link" href="https://example.com/access">Confirmar acesso</a>
      <form action="https://example.com/access"><button>Confirmar</button></form>
    ''', []);
    html.document.body!.append(frame);
    await loaded.timeout(const Duration(seconds: 5));
    final document = _inspectFrame('#inert-preview-test').contentDocument;
    final link = document.querySelector('#link');
    final button = document.querySelector('button');
    expect(link.textContent, 'Confirmar acesso');
    expect(
        document.defaultView.getComputedStyle(link).color, 'rgb(12, 34, 56)');
    link.focus();
    expect(link.matches(':focus'), isFalse);
    button.focus();
    expect(button.matches(':focus'), isFalse);
    document.documentElement.scrollTop = 300;
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(document.documentElement.scrollTop, greaterThan(0));
  });
}
