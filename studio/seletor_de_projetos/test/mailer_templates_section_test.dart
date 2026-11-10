import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/widgets/project_settings/mailer_templates_section.dart';

class FakeMailerRepository extends ProjectRepository {
  final calls = <String>[];
  bool conflict = false;
  bool wrongPassword = false;
  String body = '<p>{{ .Token }}</p>';
  String publishedBody = '<p>{{ .Token }}</p>';
  int version = 0;
  int publishedVersion = 0;
  bool hasDraft = false;
  String? confirmation;

  Map<String, dynamic> row() => {
        'kind': 'magic_link',
        'body': body,
        'published_body': publishedBody,
        'default_body': '<p>{{ .Token }}</p>',
        'version': version,
        'published_version': publishedVersion,
        'has_draft': hasDraft,
        'draft_digest': hasDraft ? 'a' * 64 : null,
        'source': publishedVersion == 0 ? 'default' : 'override',
      };

  @override
  Future<String> confirmMailerPublication(String projectRef, String kind,
      int version, String digest, String password) async {
    calls.add('CONFIRM $kind:$version:$digest');
    if (wrongPassword || password != 'current-password') {
      throw Exception('Senha atual inválida');
    }
    confirmation = 'bound-confirmation';
    return confirmation!;
  }

  @override
  Future<Map<String, dynamic>> mailerTemplatesRequest(
    String projectRef, {
    String? kind,
    String? operation,
    String method = 'GET',
    Map<String, dynamic>? body,
    String? stepUpToken,
  }) async {
    calls.add('$method ${operation ?? kind ?? 'list'}');
    if (operation == 'preview') return {'html': '<p>123456</p>'};
    if (operation == 'history/1') {
      return {'version': 1, 'body': '<p>Anterior {{ .Token }}</p>'};
    }
    if (operation == 'history') {
      return {
        'versions': [
          {
            'version': 1,
            'action': 'draft',
            'updated_at': '2026-11-10',
            'updated_by': 'admin'
          },
        ]
      };
    }
    if (operation == 'publish') {
      if (stepUpToken != confirmation || confirmation == null) {
        throw Exception('Confirmação obrigatória');
      }
      publishedBody = this.body;
      publishedVersion = ++version;
      hasDraft = false;
      return row();
    }
    if (method == 'PUT') {
      if (conflict) {
        throw Exception(
            'O template mudou. Recarregue antes de salvar novamente.');
      }
      this.body = body!['body'] as String;
      version++;
      hasDraft = true;
      return row();
    }
    if (method == 'DELETE') {
      this.body = '<p>{{ .Token }}</p>';
      version++;
      hasDraft = true;
      return {...row(), 'draft_default': true};
    }
    return {
      'templates': [row()],
      'allowed_origins': ['https://example.com']
    };
  }
}

Future<void> mount(WidgetTester tester, FakeMailerRepository repository) async {
  await tester.pumpWidget(ProviderScope(
    overrides: [projectRepositoryProvider.overrideWithValue(repository)],
    child: const MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: Padding(
          padding: EdgeInsets.all(20),
          child: MailerTemplatesSection(projectRef: 'alpha')),
    ))),
  ));
  await tester.pumpAndSettle();
}

Future<void> tapVisible(WidgetTester tester, String label) async {
  await tester.pump();
  final target = find.text(label);
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
      'saving a draft and preview leave the published template unchanged',
      (tester) async {
    final repository = FakeMailerRepository();
    await mount(tester, repository);
    await tester.enterText(
        find.byType(TextField), '<h1>Novo {{ .Token }}</h1>');
    await tapVisible(tester, 'Prévia');
    expect(find.text('Prévia com dados de exemplo'), findsOneWidget);
    await tapVisible(tester, 'Salvar rascunho');
    expect(repository.body, '<h1>Novo {{ .Token }}</h1>');
    expect(repository.publishedBody, '<p>{{ .Token }}</p>');
    expect(repository.publishedVersion, 0);
    expect(find.textContaining('rascunho pendente'), findsOneWidget);
    expect(repository.calls.where((call) => call.contains('publish')), isEmpty);
  });
  testWidgets('publication requires password confirmation of the saved draft',
      (tester) async {
    final repository = FakeMailerRepository();
    await mount(tester, repository);
    await tester.enterText(
        find.byType(TextField), '<h1>Novo {{ .Token }}</h1>');
    await tapVisible(tester, 'Salvar rascunho');
    await tapVisible(tester, 'Publicar');
    expect(repository.publishedVersion, 0);
    final password = find.widgetWithText(TextField, 'Sua senha atual');
    await tester.enterText(password, 'current-password');
    await tapVisible(tester, 'Confirmar publicação');
    expect(repository.publishedVersion, 2);
    expect(repository.publishedBody, '<h1>Novo {{ .Token }}</h1>');
    expect(repository.calls, contains('POST publish'));
  });
  testWidgets('wrong password keeps the live template and draft unchanged',
      (tester) async {
    final repository = FakeMailerRepository()..wrongPassword = true;
    await mount(tester, repository);
    await tester.enterText(
        find.byType(TextField), '<h1>Novo {{ .Token }}</h1>');
    await tapVisible(tester, 'Salvar rascunho');
    await tapVisible(tester, 'Publicar');
    await tester.enterText(
        find.widgetWithText(TextField, 'Sua senha atual'), 'wrong');
    await tapVisible(tester, 'Confirmar publicação');
    expect(find.textContaining('Senha atual inválida'), findsOneWidget);
    expect(repository.publishedVersion, 0);
    expect(repository.hasDraft, isTrue);
    await tapVisible(tester, 'Cancelar');
  });
  testWidgets('conflict retains edited HTML', (tester) async {
    final repository = FakeMailerRepository()..conflict = true;
    await mount(tester, repository);
    await tester.enterText(
        find.byType(TextField), '<h1>Não perder {{ .Token }}</h1>');
    await tapVisible(tester, 'Salvar rascunho');
    expect(find.textContaining('O template mudou.'), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '<h1>Não perder {{ .Token }}</h1>');
  });
  testWidgets('restoring history only loads the editor', (tester) async {
    final repository = FakeMailerRepository();
    await mount(tester, repository);
    await tapVisible(tester, 'Histórico');
    await tester.tap(find.textContaining('Versão 1 · Rascunho salvo'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '<p>Anterior {{ .Token }}</p>');
    expect(repository.version, 0);
    expect(repository.publishedVersion, 0);
  });
}
