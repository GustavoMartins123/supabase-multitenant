import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final favoritesProvider = AsyncNotifierProvider<FavoritesNotifier, Set<String>>(
  FavoritesNotifier.new,
);

class FavoritesNotifier extends AsyncNotifier<Set<String>> {
  @override
  Future<Set<String>> build() async {
    final prefs = await SharedPreferences.getInstance();
    final favList = prefs.getStringList('project_favorites') ?? [];
    return favList.toSet();
  }

  Future<void> toggleFavorite(String projectName) async {
    final prefs = await SharedPreferences.getInstance();
    final currentFavs = state.value ?? {};
    final newFavs = Set<String>.from(currentFavs);

    if (newFavs.contains(projectName)) {
      newFavs.remove(projectName);
    } else {
      newFavs.add(projectName);
    }

    state = AsyncData(newFavs);
    await prefs.setStringList('project_favorites', newFavs.toList());
  }

  Future<void> removeFavorite(String projectName) async {
    final prefs = await SharedPreferences.getInstance();
    final currentFavs = state.value ?? {};
    if (!currentFavs.contains(projectName)) return;

    final newFavs = Set<String>.from(currentFavs);
    newFavs.remove(projectName);
    state = AsyncData(newFavs);
    await prefs.setStringList('project_favorites', newFavs.toList());
  }
}
