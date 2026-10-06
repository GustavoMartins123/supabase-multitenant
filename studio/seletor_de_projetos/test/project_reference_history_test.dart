import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/models/project_collaboration.dart';

void main() {
  final event = {
    'id': 42,
    'action': 'project_rename_succeeded',
    'actor_name': 'Admin',
    'old_value': {'ref': 'aaaaaaaaaaaaaaaaaaaa'},
    'new_value': {'ref': 'bbbbbbbbbbbbbbbbbbbb'},
    'created_at': '2026-10-03T20:00:00Z',
  };

  test('history describes URL rotation without changing the technical name',
      () {
    final parsed = ProjectRenameEvent.fromJson(event);
    expect(parsed.label, 'Troca de URL concluída');
    expect(parsed.oldValue!['ref'], 'aaaaaaaaaaaaaaaaaaaa');
    expect(parsed.newValue!['ref'], 'bbbbbbbbbbbbbbbbbbbb');
  });

  test('invalid history timestamp is not replaced by the current time', () {
    expect(
      () => ProjectRenameEvent.fromJson({...event, 'created_at': 'invalid'}),
      throwsFormatException,
    );
  });
}
