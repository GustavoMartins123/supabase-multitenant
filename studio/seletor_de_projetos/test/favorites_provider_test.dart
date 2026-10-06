import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seletor_de_projetos/providers/favorites_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('only canonical UUID preferences are loaded', () async {
    SharedPreferences.setMockInitialValues({
      'project_favorites': <String>['technical_project']
    });
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(await container.read(favoritesProvider.future), isEmpty);
    await container
        .read(favoritesProvider.notifier)
        .toggleFavorite('11111111-1111-4111-8111-111111111111');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('project_favorite_ids'),
        ['11111111-1111-4111-8111-111111111111']);
  });
  test('URL rotation does not change stored project UUID favorites', () async {
    SharedPreferences.setMockInitialValues({
      'project_favorite_ids': <String>['11111111-1111-4111-8111-111111111111']
    });
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(await container.read(favoritesProvider.future),
        {'11111111-1111-4111-8111-111111111111'});
    await container
        .read(favoritesProvider.notifier)
        .toggleFavorite('22222222-2222-4222-8222-222222222222');
    expect(container.read(favoritesProvider).requireValue.length, 2);
  });
  test('invalid canonical preferences fail without overwriting them', () async {
    SharedPreferences.setMockInitialValues({
      'project_favorite_ids': <String>['technical_project']
    });
    final container = ProviderContainer(retry: (count, error) => null);
    addTearDown(container.dispose);
    await expectLater(
        container.read(favoritesProvider.future), throwsFormatException);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('project_favorite_ids'), ['technical_project']);
  });
  test('public references cannot be stored instead of project UUIDs', () async {
    SharedPreferences.setMockInitialValues({});
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await expectLater(
      container
          .read(favoritesProvider.notifier)
          .toggleFavorite('abcdefghijklmnopqrst'),
      throwsFormatException,
    );
    expect(await container.read(favoritesProvider.future), isEmpty);
  });
}
