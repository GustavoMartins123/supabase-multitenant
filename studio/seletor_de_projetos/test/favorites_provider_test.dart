import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seletor_de_projetos/data/project_repository.dart';
import 'package:seletor_de_projetos/providers/favorites_provider.dart';

class FixtureRepository extends ProjectRepository {
  @override
  Future<List<Map<String, dynamic>>> fetchProjects({dynamic cancellation}) async => [
    {'id': '11111111-1111-4111-8111-111111111111', 'name': 'technical_project', 'public_ref': 'abcdefghijklmnopqrst'},
  ];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('favorites migrate once from technical names to stable UUIDs', () async {
    SharedPreferences.setMockInitialValues({'project_favorites': <String>['technical_project']});
    final container = ProviderContainer(retry: (count, error) => null, overrides: [projectRepositoryProvider.overrideWithValue(FixtureRepository())]);
    addTearDown(container.dispose);
    expect(await container.read(favoritesProvider.future), {'11111111-1111-4111-8111-111111111111'});
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('project_favorites'), isNull);
    expect(prefs.getStringList('project_favorite_ids'), ['11111111-1111-4111-8111-111111111111']);
  });
  test('URL rotation does not change stored project UUID favorites', () async {
    SharedPreferences.setMockInitialValues({'project_favorite_ids': <String>['11111111-1111-4111-8111-111111111111']});
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(await container.read(favoritesProvider.future), {'11111111-1111-4111-8111-111111111111'});
    await container.read(favoritesProvider.notifier).toggleFavorite('22222222-2222-4222-8222-222222222222');
    expect(container.read(favoritesProvider).requireValue.length, 2);
  });
  test('unknown legacy favorites fail explicitly without overwriting preferences', () async {
    SharedPreferences.setMockInitialValues({'project_favorites': <String>['unknown_project']});
    final container = ProviderContainer(retry: (count, error) => null, overrides: [projectRepositoryProvider.overrideWithValue(FixtureRepository())]);
    addTearDown(container.dispose);
    await expectLater(container.read(favoritesProvider.future), throwsFormatException);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('project_favorites'), ['unknown_project']);
    expect(prefs.getStringList('project_favorite_ids'), isNull);
  });
}
