import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../data/project_repository.dart';

final favoritesProvider = AsyncNotifierProvider<FavoritesNotifier, Set<String>>(
  FavoritesNotifier.new,
);

class FavoritesNotifier extends AsyncNotifier<Set<String>> {
  @override
  Future<Set<String>> build() async {
    final prefs = await SharedPreferences.getInstance();
    final ids = prefs.getStringList('project_favorite_ids');
    if (ids != null) return ids.toSet();
    final names = prefs.getStringList('project_favorites');
    final migrated = <String>{};
    if (names != null && names.isNotEmpty) {
      final projects =
          await ref.read(projectRepositoryProvider).fetchProjects();
      for (final name in names) {
        final matches =
            projects.where((project) => project['name'] == name).toList();
        if (matches.length != 1 || matches.single['id'] is! String) {
          throw FormatException('Favorito antigo sem projeto acessivel: $name');
        }
        migrated.add(matches.single['id'] as String);
      }
    }
    if (!await prefs.setStringList('project_favorite_ids', migrated.toList())) {
      throw StateError('Falha ao migrar favoritos');
    }
    await prefs.remove('project_favorites');
    return migrated;
  }

  Future<void> toggleFavorite(String projectName) async {
    final prefs = await SharedPreferences.getInstance();
    final currentFavs = await future;
    final newFavs = Set<String>.from(currentFavs);

    if (newFavs.contains(projectName)) {
      newFavs.remove(projectName);
    } else {
      newFavs.add(projectName);
    }

    if (!await prefs.setStringList('project_favorite_ids', newFavs.toList())) {
      throw StateError('Falha ao salvar favoritos');
    }
    state = AsyncData(newFavs);
  }

  Future<void> removeFavorite(String projectName) async {
    final prefs = await SharedPreferences.getInstance();
    final currentFavs = await future;
    if (!currentFavs.contains(projectName)) return;

    final newFavs = Set<String>.from(currentFavs);
    newFavs.remove(projectName);
    if (!await prefs.setStringList('project_favorite_ids', newFavs.toList())) {
      throw StateError('Falha ao salvar favoritos');
    }
    state = AsyncData(newFavs);
  }
}
