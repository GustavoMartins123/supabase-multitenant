import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/project_repository.dart';
import '../models/opaque_api_key.dart';

final opaqueApiKeysProvider = AsyncNotifierProvider.autoDispose
    .family<OpaqueApiKeysController, OpaqueApiKeysState, String>(
  OpaqueApiKeysController.new,
  retry: (_, __) => null,
);

enum OpaqueApiKeyOperationKind {
  prepareMigration,
  abortMigration,
  cutoverMigration,
  claimReveal,
  confirmInstallation,
  rotateSlot,
  disableSlot,
  updateAutomaticRotation,
  updateExpirationPolicy,
  cancelPendingRotation,
  createSlot,
}

enum OpaqueApiKeyOperationTarget { project, slot, reveal }

final class OpaqueApiKeyOperation {
  const OpaqueApiKeyOperation.project(this.kind)
      : target = OpaqueApiKeyOperationTarget.project,
        targetId = null;

  const OpaqueApiKeyOperation.slot(this.kind, this.targetId)
      : target = OpaqueApiKeyOperationTarget.slot;

  const OpaqueApiKeyOperation.reveal(this.targetId)
      : kind = OpaqueApiKeyOperationKind.claimReveal,
        target = OpaqueApiKeyOperationTarget.reveal;

  final OpaqueApiKeyOperationKind kind;
  final OpaqueApiKeyOperationTarget target;
  final String? targetId;

  @override
  bool operator ==(Object other) =>
      other is OpaqueApiKeyOperation &&
      other.kind == kind &&
      other.target == target &&
      other.targetId == targetId;

  @override
  int get hashCode => Object.hash(kind, target, targetId);
}

final class OpaqueApiKeysState {
  OpaqueApiKeysState({
    required Map<String, dynamic> migration,
    required List<OpaqueApiKeySlot> slots,
    required List<OpaqueApiKeyReveal> reveals,
    Set<OpaqueApiKeyOperation> operations = const {},
    this.isRefreshing = false,
    this.synchronizationError,
  })  : migration = Map.unmodifiable(migration),
        slots = List.unmodifiable(slots),
        reveals = List.unmodifiable(reveals),
        operations = Set.unmodifiable(operations);

  final Map<String, dynamic> migration;
  final List<OpaqueApiKeySlot> slots;
  final List<OpaqueApiKeyReveal> reveals;
  final Set<OpaqueApiKeyOperation> operations;
  final bool isRefreshing;
  final String? synchronizationError;

  bool get hasActiveOperation => operations.isNotEmpty;

  bool get hasProjectOperation => operations.any(
        (operation) => operation.target == OpaqueApiKeyOperationTarget.project,
      );

  bool isSlotBusy(String slotId) => operations.any(
        (operation) =>
            operation.target == OpaqueApiKeyOperationTarget.slot &&
            operation.targetId == slotId,
      );

  bool isRevealBusy(String keyId) => operations.any(
        (operation) =>
            operation.target == OpaqueApiKeyOperationTarget.reveal &&
            operation.targetId == keyId,
      );

  bool get actionsLocked =>
      isRefreshing || hasActiveOperation || synchronizationError != null;

  OpaqueApiKeysState copyWith({
    Map<String, dynamic>? migration,
    List<OpaqueApiKeySlot>? slots,
    List<OpaqueApiKeyReveal>? reveals,
    Set<OpaqueApiKeyOperation>? operations,
    bool? isRefreshing,
    String? synchronizationError,
    bool clearSynchronizationError = false,
  }) {
    assert(!(clearSynchronizationError && synchronizationError != null));
    return OpaqueApiKeysState(
      migration: migration ?? this.migration,
      slots: slots ?? this.slots,
      reveals: reveals ?? this.reveals,
      operations: operations ?? this.operations,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      synchronizationError: clearSynchronizationError
          ? null
          : synchronizationError ?? this.synchronizationError,
    );
  }
}

final class OpaqueApiKeysController extends AsyncNotifier<OpaqueApiKeysState> {
  OpaqueApiKeysController(this.projectRef);

  final String projectRef;

  @override
  Future<OpaqueApiKeysState> build() {
    return _fetch(ref.watch(projectRepositoryProvider));
  }

  Future<void> refresh() async {
    final current = state.value;
    if (current == null) {
      state = const AsyncLoading();
      state = await AsyncValue.guard(
        () => _fetch(ref.read(projectRepositoryProvider)),
      );
      return;
    }
    if (current.isRefreshing || current.hasActiveOperation) {
      throw StateError('Já existe uma operação de API key em andamento.');
    }

    state = AsyncData(current.copyWith(isRefreshing: true));
    try {
      final refreshed = await _fetch(ref.read(projectRepositoryProvider));
      if (ref.mounted) state = AsyncData(refreshed);
    } catch (error) {
      if (!ref.mounted) return;
      state = AsyncData(
        current.copyWith(
          isRefreshing: false,
          synchronizationError:
              'Não foi possível sincronizar o estado das API keys: '
              '${opaqueApiKeyErrorMessage(error)}',
        ),
      );
    }
  }

  Future<void> prepareMigration() => _runAndSynchronize(
        const OpaqueApiKeyOperation.project(
          OpaqueApiKeyOperationKind.prepareMigration,
        ),
        (repository) async {
          await repository.prepareOpaqueApiKeyMigration(projectRef);
        },
      );

  Future<void> abortMigration() => _runAndSynchronize(
        const OpaqueApiKeyOperation.project(
          OpaqueApiKeyOperationKind.abortMigration,
        ),
        (repository) async {
          await repository.abortOpaqueApiKeyMigration(projectRef);
        },
      );

  Future<void> cutoverMigration() => _runAndSynchronize(
        const OpaqueApiKeyOperation.project(
          OpaqueApiKeyOperationKind.cutoverMigration,
        ),
        (repository) async {
          await repository.cutoverOpaqueApiKeyMigration(projectRef);
        },
      );

  Future<String> claimReveal(
    String keyId, {
    String? stepUpToken,
  }) =>
      _runSecretCommand(
        OpaqueApiKeyOperation.reveal(keyId),
        (repository) => repository.claimOpaqueApiKey(
          projectRef,
          keyId,
          stepUpToken: stepUpToken,
        ),
        onSuccess: (current) => current.copyWith(
          reveals: current.reveals
              .where((reveal) => reveal.keyId != keyId)
              .toList(growable: false),
        ),
      );

  Future<void> confirmInstallation(String slotId, String keyId) =>
      _runAndSynchronize(
        OpaqueApiKeyOperation.slot(
          OpaqueApiKeyOperationKind.confirmInstallation,
          slotId,
        ),
        (repository) => repository.confirmOpaqueApiKeyInstallation(
          projectRef,
          slotId,
          keyId,
        ),
      );

  Future<IssuedOpaqueApiKey> rotateSlot(
    String slotId, {
    String? stepUpToken,
  }) =>
      _runSecretCommand(
        OpaqueApiKeyOperation.slot(
          OpaqueApiKeyOperationKind.rotateSlot,
          slotId,
        ),
        (repository) => repository.rotateOpaqueApiKeySlot(
          projectRef,
          slotId,
          stepUpToken: stepUpToken,
        ),
      );

  Future<void> disableSlot(String slotId) => _runAndSynchronize(
        OpaqueApiKeyOperation.slot(
          OpaqueApiKeyOperationKind.disableSlot,
          slotId,
        ),
        (repository) => repository.disableOpaqueApiKeySlot(projectRef, slotId),
      );

  Future<void> updateAutomaticRotation(String slotId, bool enabled) =>
      _runAndSynchronize(
        OpaqueApiKeyOperation.slot(
          OpaqueApiKeyOperationKind.updateAutomaticRotation,
          slotId,
        ),
        (repository) => repository.updateOpaqueApiKeySlot(
          projectRef,
          slotId,
          automaticRotationEnabled: enabled,
        ),
      );

  Future<void> updateExpirationPolicy(String slotId, int? days) =>
      _runAndSynchronize(
        OpaqueApiKeyOperation.slot(
          OpaqueApiKeyOperationKind.updateExpirationPolicy,
          slotId,
        ),
        (repository) => repository.updateOpaqueApiKeySlot(
          projectRef,
          slotId,
          automaticRotationEnabled: days == null ? false : null,
          expirationPolicy: OpaqueApiKeyExpirationPolicyUpdate(days),
        ),
      );

  Future<void> cancelPendingRotation(String slotId) => _runAndSynchronize(
        OpaqueApiKeyOperation.slot(
          OpaqueApiKeyOperationKind.cancelPendingRotation,
          slotId,
        ),
        (repository) =>
            repository.cancelOpaqueApiKeyRotation(projectRef, slotId),
      );

  Future<IssuedOpaqueApiKey> createSlot({
    required String name,
    required String kind,
    required List<String> allowedServices,
    required bool automaticRotationEnabled,
    required int? rotationIntervalDays,
    String? stepUpToken,
  }) =>
      _runSecretCommand(
        const OpaqueApiKeyOperation.project(
          OpaqueApiKeyOperationKind.createSlot,
        ),
        (repository) => repository.createOpaqueApiKeySlot(
          projectRef,
          name: name,
          kind: kind,
          allowedServices: allowedServices,
          automaticRotationEnabled: automaticRotationEnabled,
          rotationIntervalDays: rotationIntervalDays,
          stepUpToken: stepUpToken,
        ),
      );

  Future<OpaqueApiKeysState> _fetch(ProjectRepository repository) async {
    final values = await Future.wait([
      repository.fetchOpaqueApiKeyMigration(projectRef),
      repository.fetchOpaqueApiKeySlots(projectRef),
      repository.fetchOpaqueApiKeyReveals(projectRef),
    ]);
    return OpaqueApiKeysState(
      migration: values[0] as Map<String, dynamic>,
      slots: values[1] as List<OpaqueApiKeySlot>,
      reveals: values[2] as List<OpaqueApiKeyReveal>,
    );
  }

  Future<void> _runAndSynchronize(
    OpaqueApiKeyOperation operation,
    Future<void> Function(ProjectRepository repository) command,
  ) async {
    _begin(operation);
    final repository = ref.read(projectRepositoryProvider);
    var commandCompleted = false;
    try {
      await command(repository);
      commandCompleted = true;
      if (!ref.mounted) return;
      final refreshed = await _fetch(repository);
      if (ref.mounted) state = AsyncData(refreshed);
    } catch (error, stackTrace) {
      if (ref.mounted) {
        final current = state.requireValue;
        state = AsyncData(
          commandCompleted
              ? current.copyWith(
                  operations: const {},
                  synchronizationError:
                      'A operação foi concluída, mas o estado atualizado não '
                      'pôde ser carregado: ${opaqueApiKeyErrorMessage(error)}',
                )
              : current.copyWith(operations: const {}),
        );
      }
      if (commandCompleted) return;
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  Future<T> _runSecretCommand<T>(
    OpaqueApiKeyOperation operation,
    Future<T> Function(ProjectRepository repository) command, {
    OpaqueApiKeysState Function(OpaqueApiKeysState current)? onSuccess,
  }) async {
    _begin(operation);
    try {
      final result = await command(ref.read(projectRepositoryProvider));
      if (ref.mounted) {
        final current = state.requireValue;
        final updated = onSuccess?.call(current) ?? current;
        state = AsyncData(updated.copyWith(operations: const {}));
      }
      return result;
    } catch (error, stackTrace) {
      if (ref.mounted) {
        state = AsyncData(
          state.requireValue.copyWith(operations: const {}),
        );
      }
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  void _begin(OpaqueApiKeyOperation operation) {
    final current = state.value;
    if (current == null) {
      throw StateError('O estado das API keys ainda não foi carregado.');
    }
    if (current.actionsLocked) {
      throw StateError(
        current.synchronizationError != null
            ? 'Sincronize o estado das API keys antes de continuar.'
            : 'Já existe uma operação de API key em andamento.',
      );
    }
    state = AsyncData(
      current.copyWith(operations: {operation}),
    );
  }
}

String opaqueApiKeyErrorMessage(Object error) =>
    error.toString().replaceFirst('Exception: ', '');
