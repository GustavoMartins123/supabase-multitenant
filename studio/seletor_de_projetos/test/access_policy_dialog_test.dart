import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:seletor_de_projetos/models/access_policy.dart';
import 'package:seletor_de_projetos/services/access_policy_service.dart';
import 'package:seletor_de_projetos/widgets/project_settings/access_policy_dialog.dart';

Map<String, dynamic> policy(
        {String mode = 'restrict', List<String>? countries = const ['BR']}) =>
    {
      'geo_mode': mode,
      'allowed_countries': countries,
      'allowed_networks': <String>[],
      'rate_limit': null,
      'request_quota': null
    };

class FakeService extends AccessPolicyService {
  Map<String, dynamic>? saved;
  int reads = 0;
  @override
  Future<AccessPolicySnapshot> get(String project, String? slot) async {
    reads++;
    return AccessPolicySnapshot.fromJson({
      'scope': 'slot',
      'scope_id': 'slot-id',
      'revision': 1,
      'policy': policy(),
      'project_policy': policy(mode: 'unrestricted', countries: null)
    });
  }

  @override
  Future<List<AccessCountry>> countries() async => [
        AccessCountry.fromJson(
            {'code': 'BR', 'name': 'Brasil', 'name_en': 'Brazil'}),
        AccessCountry.fromJson(
            {'code': 'PT', 'name': 'Portugal', 'name_en': 'Portugal'}),
        AccessCountry.fromJson({
          'code': 'US',
          'name': 'Estados Unidos',
          'name_en': 'United States'
        })
      ];
  @override
  Future<AccessPolicySnapshot> save(String project, String? slot, int revision,
      Map<String, dynamic> value, String? stepUp) async {
    saved = value;
    return AccessPolicySnapshot.fromJson({
      'scope': 'slot',
      'scope_id': 'slot-id',
      'revision': 2,
      'policy': value,
      'project_policy': policy(mode: 'unrestricted', countries: null)
    });
  }
}

void main() {
  Future<void> open(WidgetTester tester, FakeService service) async {
    await tester.binding.setSurfaceSize(const Size(1000, 1300));
    await tester.pumpWidget(ProviderScope(
        child: MaterialApp(
            home: AccessPolicyDialog(
                projectRef: 'project', slotId: 'slot-id', service: service))));
    await tester.pumpAndSettle();
  }

  test('malformed policy is not replaced by unrestricted settings', () {
    expect(() => validateAccessPolicy({}), throwsFormatException);
    expect(
        () => validateAccessPolicy({
              ...policy(),
              'rate_limit': {'requests_per_second': '10', 'burst': 20}
            }),
        throwsFormatException);
  });
  testWidgets(
      'search preserves hidden selections and select all covers catalog',
      (tester) async {
    final service = FakeService();
    await open(tester, service);
    await tester.enterText(
        find.widgetWithText(TextField, 'Buscar país ou código'), 'Portugal');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('country-PT')));
    await tester.pump();
    expect(find.text('2 de 3 países e territórios'), findsOneWidget);
    await tester.tap(find.text('Selecionar todos'));
    await tester.pump();
    expect(find.text('3 de 3 países e territórios'), findsOneWidget);
    await tester.tap(find.text('Salvar'));
    await tester.pumpAndSettle();
    expect(service.saved!['allowed_countries'],
        unorderedEquals(['BR', 'PT', 'US']));
    expect(tester.takeException(), isNull);
    service.close();
  });
  testWidgets('empty country selection is explicit, not unrestricted',
      (tester) async {
    final service = FakeService();
    await open(tester, service);
    await tester.tap(find.text('Limpar seleção'));
    await tester.pump();
    await tester.tap(find.text('Salvar'));
    await tester.pumpAndSettle();
    expect(service.saved!['allowed_countries'], isEmpty);
    expect(service.saved!['geo_mode'], 'restrict');
    service.close();
  });
  testWidgets('no background usage or policy polling', (tester) async {
    final service = FakeService();
    await open(tester, service);
    await tester.pump(const Duration(minutes: 1));
    expect(service.reads, 1);
    expect(service.saved, isNull);
    service.close();
  });
}
