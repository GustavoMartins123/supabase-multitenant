import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../lib/providers/favorites_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('renameFavorite migrates the persisted slug', () async {
    SharedPreferences.setMockInitialValues({
      'project_favorites': <String>['old_project', 'other_project'],
    });
    final container = ProviderContainer();
    addTearDown(container.dispose);

    await container.read(favoritesProvider.future);
    await container
        .read(favoritesProvider.notifier)
        .renameFavorite('old_project', 'new_project');

    expect(
      container.read(favoritesProvider).requireValue,
      <String>{'new_project', 'other_project'},
    );
    final preferences = await SharedPreferences.getInstance();
    expect(
      preferences.getStringList('project_favorites')?.toSet(),
      <String>{'new_project', 'other_project'},
    );
  });

  test('renameFavorite leaves non-favorites unchanged', () async {
    SharedPreferences.setMockInitialValues({
      'project_favorites': <String>['other_project'],
    });
    final container = ProviderContainer();
    addTearDown(container.dispose);

    await container.read(favoritesProvider.future);
    await container
        .read(favoritesProvider.notifier)
        .renameFavorite('old_project', 'new_project');

    expect(
      container.read(favoritesProvider).requireValue,
      <String>{'other_project'},
    );
  });
}
