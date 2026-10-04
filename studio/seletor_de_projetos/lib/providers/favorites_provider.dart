import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final favoritesProvider = AsyncNotifierProvider<FavoritesNotifier, Set<String>>(
  FavoritesNotifier.new,
);

class FavoritesNotifier extends AsyncNotifier<Set<String>> {
  @override
  Future<Set<String>> build() async {
    final prefs = await SharedPreferences.getInstance();
    final ids = prefs.getStringList('project_favorite_ids');
    if (ids == null) return <String>{};
    for (final id in ids) {
      _validateProjectUuid(id);
    }
    return ids.toSet();
  }

  void _validateProjectUuid(String projectUuid) {
    if (!RegExp(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        .hasMatch(projectUuid)) {
      throw const FormatException('Favorito sem UUID de projeto canonico');
    }
  }

  Future<void> toggleFavorite(String projectUuid) async {
    _validateProjectUuid(projectUuid);
    final prefs = await SharedPreferences.getInstance();
    final currentFavs = await future;
    final newFavs = Set<String>.from(currentFavs);

    if (newFavs.contains(projectUuid)) {
      newFavs.remove(projectUuid);
    } else {
      newFavs.add(projectUuid);
    }

    if (!await prefs.setStringList('project_favorite_ids', newFavs.toList())) {
      throw StateError('Falha ao salvar favoritos');
    }
    state = AsyncData(newFavs);
  }

  Future<void> removeFavorite(String projectUuid) async {
    _validateProjectUuid(projectUuid);
    final prefs = await SharedPreferences.getInstance();
    final currentFavs = await future;
    if (!currentFavs.contains(projectUuid)) return;

    final newFavs = Set<String>.from(currentFavs);
    newFavs.remove(projectUuid);
    if (!await prefs.setStringList('project_favorite_ids', newFavs.toList())) {
      throw StateError('Falha ao salvar favoritos');
    }
    state = AsyncData(newFavs);
  }
}
