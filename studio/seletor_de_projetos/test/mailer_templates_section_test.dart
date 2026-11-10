import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/widgets/project_settings/mailer_templates_section.dart';
import 'package:seletor_de_projetos/widgets/project_settings/mailer_preview_panel.dart';

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
  final previewBodies = <String>[];
  bool deferPreview = false;
  final previews = <Completer<Map<String, dynamic>>>[];

  @override
  Future<Map<String, dynamic>> fetchConfig() async =>
      {'server_domain': 'https://example.com'};
  @override
  Future<List<Map<String, dynamic>>> getMembers(String projectRef) async => [
        {'user_id': 'admin', 'role': 'admin'}
      ];
  @override
  Future<Map<String, dynamic>> getFullStatus(String projectRef) async =>
      {'containers': []};

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
    if (operation == 'preview') {
      previewBodies.add(body!['body'] as String);
      if (deferPreview) {
        final request = Completer<Map<String, dynamic>>();
        previews.add(request);
        return request.future;
      }
      return {'html': '<p>123456</p>'};
    }
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
    await tester.tap(find.byTooltip('Fechar prévia'));
    await tester.pumpAndSettle();
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
  testWidgets(
      'desktop preview stays beside the editable HTML and refreshes without saving',
      (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final repository = FakeMailerRepository();
    await tester.pumpWidget(ProviderScope(
      overrides: [projectRepositoryProvider.overrideWithValue(repository)],
      child: const MaterialApp(home: PreviewHarness()),
    ));
    await tester.pumpAndSettle();
    final panel = find.byKey(const ValueKey('mailer-preview-panel'));
    expect(panel, findsOneWidget);
    expect(tester.getRect(panel).left,
        greaterThan(tester.getRect(find.byType(TextField)).right));
    await tester.enterText(
        find.byType(TextField), '<h1>Sem salvar {{ .Token }}</h1>');
    await tester.pump(const Duration(milliseconds: 2300));
    await tester.pumpAndSettle();
    expect(repository.previewBodies.last, '<h1>Sem salvar {{ .Token }}</h1>');
    expect(repository.version, 0);
    expect(repository.publishedVersion, 0);
    await tester.tap(find.byTooltip('Fechar prévia'));
    await tester.pumpAndSettle();
    expect(panel, findsNothing);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '<h1>Sem salvar {{ .Token }}</h1>');
    expect(tester.takeException(), isNull);
  });

  testWidgets('small screen preview closes back to the same unsaved editor',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final repository = FakeMailerRepository();
    await tester.pumpWidget(ProviderScope(
      overrides: [projectRepositoryProvider.overrideWithValue(repository)],
      child: const MaterialApp(home: PreviewHarness()),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('mailer-preview-panel')), findsOneWidget);
    await tester.tap(find.byTooltip('Fechar prévia'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byType(TextField), '<p>Continuar {{ .Token }}</p>');
    await tapVisible(tester, 'Prévia');
    await tester.tap(find.byTooltip('Fechar prévia'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '<p>Continuar {{ .Token }}</p>');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a late preview response cannot replace newer HTML',
      (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final repository = FakeMailerRepository()..deferPreview = true;
    await tester.pumpWidget(ProviderScope(
      overrides: [projectRepositoryProvider.overrideWithValue(repository)],
      child: const MaterialApp(home: PreviewHarness()),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1));
    await tester.enterText(
        find.byType(TextField), '<h1>Atual {{ .Token }}</h1>');
    await tester.pump(const Duration(milliseconds: 2300));
    expect(repository.previews.length, 2);
    repository.previews.last.complete({'html': '<p>Atual 123456</p>'});
    await tester.pumpAndSettle();
    repository.previews.first.complete({'html': '<p>Antigo 123456</p>'});
    await tester.pumpAndSettle();
    expect(find.text('<p>Atual 123456</p>'), findsOneWidget);
    expect(find.text('<p>Antigo 123456</p>'), findsNothing);
  });

  testWidgets('preview controls fit a narrow screen with enlarged text',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(ProviderScope(
      overrides: [
        projectRepositoryProvider.overrideWithValue(FakeMailerRepository())
      ],
      child: MaterialApp(
        builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: TextScaler.linear(2)),
            child: child!),
        home: const PreviewHarness(),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('mailer-preview-panel')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class PreviewHarness extends StatefulWidget {
  const PreviewHarness({super.key});
  @override
  State<PreviewHarness> createState() => _PreviewHarnessState();
}

class _PreviewHarnessState extends State<PreviewHarness> {
  final _editorKey = GlobalKey();
  MailerPreviewData? _preview;

  @override
  Widget build(BuildContext context) => Scaffold(
          body: MailerPreviewLayout(
        preview: _preview,
        editor: SingleChildScrollView(
          key: _editorKey,
          padding: const EdgeInsets.all(20),
          child: MailerTemplatesSection(
              projectRef: 'alpha',
              onPreviewChanged: (data) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted) setState(() => _preview = data);
                });
              }),
        ),
      ));
}
