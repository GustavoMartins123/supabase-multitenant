import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/project_repository.dart';

final configProvider =
    AsyncNotifierProvider<ConfigNotifier, Map<String, dynamic>?>(
      ConfigNotifier.new,
    );

class ConfigNotifier extends AsyncNotifier<Map<String, dynamic>?> {
  @override
  Future<Map<String, dynamic>?> build() async {
    return ref.watch(projectRepositoryProvider).fetchConfig();
  }
}
