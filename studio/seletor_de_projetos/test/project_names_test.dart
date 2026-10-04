import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/duplicate_project_dialog.dart';
import 'package:seletor_de_projetos/new_project_dialog.dart';
import 'package:seletor_de_projetos/utils/project_name_validator.dart';

void main() {
  test('names are shape-checked, not blocked by SQL or HTTP namespaces', () {
    for (final name in ['select', 'default', 'table', 'internal', 'admin', 'phpmyadmin']) {
      expect(ProjectNameValidator.isValidShape(name), isTrue);
    }
    for (final name in ['../admin', 'a/b', 'a.b', 'a', '4name', 'x' * 41]) {
      expect(ProjectNameValidator.isValidShape(name), isFalse);
    }
  });

  testWidgets('new project offers more default names', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: NewProjectDialog())));
    await tester.pumpAndSettle();
    final autocomplete = tester.widget<RawAutocomplete<String>>(
        find.byType(RawAutocomplete<String>));
    final options = await autocomplete.optionsBuilder(const TextEditingValue());
    expect(options.length, greaterThan(10));
    expect(options, containsAll(['portal_clientes', 'loja_online']));
    await tester.enterText(find.byType(TextFormField), 'select');
    await tester.pumpAndSettle();
    final form = tester.state<FormState>(find.byType(Form));
    expect(form.validate(), isTrue);
  });

  testWidgets('duplicate keeps suffixes distinct even for a forty-letter name', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body:
        DuplicateProjectDialog(originalProjectName: 'x' * 40))));
    await tester.pumpAndSettle();
    final controller = tester.widget<TextFormField>(find.byType(TextFormField)).controller!;
    expect(controller.text, '${'x' * 35}_copy');
    expect(find.text('${'x' * 33}_backup'), findsOneWidget);
    expect(find.text('${'x' * 34}_clone'), findsOneWidget);
    expect(tester.state<FormState>(find.byType(Form)).validate(), isTrue);
  });
}
