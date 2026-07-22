import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/widgets/error_box.dart';

void main() {
  testWidgets('anuncia o erro e oferece uma acao de retry acessivel', (
    tester,
  ) async {
    var retried = false;
    final semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ErrorBox(
            message: 'Falha ao carregar membros',
            onRetry: () => retried = true,
          ),
        ),
      ),
    );

    expect(
      find.bySemanticsLabel('Erro: Falha ao carregar membros'),
      findsOneWidget,
    );
    expect(find.bySemanticsLabel('Tentar novamente'), findsOneWidget);

    await tester.tap(find.text('Tentar novamente'));
    expect(retried, isTrue);
    semantics.dispose();
  });
}
