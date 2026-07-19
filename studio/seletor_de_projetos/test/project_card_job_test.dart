import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/models/job.dart';
import 'package:seletor_de_projetos/widgets/project_card.dart';

void main() {
  testWidgets('project card renders durable job progress', (tester) async {
    const job = Job(
      'job-1',
      project: 'meu_projeto',
      action: 'create',
      status: 'running',
      message: 'Provisionando infraestrutura do projeto...',
      progress: 10,
      currentStep: 'provision_infrastructure',
    );

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 380,
                height: 280,
                child: ProjectCard(
                  refKey: 'meu_projeto',
                  anonKey: '',
                  activeJob: job,
                  isFavorite: false,
                  onTap: () {},
                  onDeleted: () {},
                  onDuplicate: () {},
                  onToggleFavorite: () {},
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('meu_projeto'), findsOneWidget);
    expect(find.text('CRIANDO PROJETO · EM EXECUÇÃO'), findsOneWidget);
    expect(
      find.text('Provisionando infraestrutura do projeto...'),
      findsOneWidget,
    );
    expect(find.text('provision_infrastructure'), findsOneWidget);
    expect(find.text('10%'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
  });
}
