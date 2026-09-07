import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:projects_api_client/api.dart' as generated;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/job.dart';
import '../models/project_collaboration.dart';
import '../models/restore_point.dart';
import '../models/user_models.dart';
import '../models/project_user_telemetry.dart';
import '../models/opaque_api_key.dart';
import '../session.dart';
import 'api_client.dart';

final projectRepositoryProvider = Provider((ref) {
  final repository = ProjectRepository();
  ref.onDispose(repository.close);
  return repository;
});

class ProjectActionResult {
  const ProjectActionResult({this.message, this.job});

  final String? message;
  final Job? job;
}

class UpdateSettingsResult {
  const UpdateSettingsResult({
    required this.affectedServices,
    this.storageLimitToken,
  });

  final List<String> affectedServices;
  final String? storageLimitToken;
}

class OpaqueApiKeyExpirationPolicyUpdate {
  const OpaqueApiKeyExpirationPolicyUpdate(this.rotationIntervalDays);

  final int? rotationIntervalDays;
}

class ProjectSettingsData {
  const ProjectSettingsData({
    required this.settings,
    required this.pendingAffectedServices,
    this.storageLimitToken,
  });

  final Map<String, String> settings;
  final List<String> pendingAffectedServices;
  final String? storageLimitToken;
}

class ProjectRepository {
  ProjectRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  void close() => _client.close();

  Map<String, dynamic>? _tryDecodeObject(String body) {
    return tryDecodeJsonObjectBody(body);
  }

  String? _extractMessage(http.Response resp) {
    final data = _tryDecodeObject(resp.body);
    final message = data?['message'];
    return message == null || message.toString().isEmpty
        ? null
        : message.toString();
  }

  Never _throwParsedError(http.Response resp) {
    throw ApiException.fromResponse(resp);
  }

  void _ensureCommandSucceeded(
    http.Response resp, {
    Set<int> allowedStatusCodes = const {200},
  }) {
    if (!allowedStatusCodes.contains(resp.statusCode)) {
      _throwParsedError(resp);
    }

    if (resp.body.isEmpty) return;

    final data = _tryDecodeObject(resp.body);
    if (data != null) {
      final success = data['success'];
      final errors = data['errors'];

      if (success == false || (errors is List && errors.isNotEmpty)) {
        _throwParsedError(resp);
      }
    }
  }

  Future<Map<String, dynamic>> fetchConfig() async {
    final response = await _client.get(Uri.parse('/api/config'));
    _ensureCommandSucceeded(response);
    return decodeJsonObject(
      response,
      context: 'Configuracao do Studio',
    );
  }

  Future<List<Map<String, dynamic>>> fetchProjects({
    RequestCancellation? cancellation,
  }) async {
    final response = await _client.get(
      Uri.parse('/api/projects'),
      cancellation: cancellation,
    );
    _ensureCommandSucceeded(response);
    final decoded = decodeJsonList(
      response,
      context: 'Lista de projetos',
    );
    final projects = <Map<String, dynamic>>[];
    for (final item in decoded) {
      if (item is! Map) {
        throw const ApiException(
          ApiFailureKind.invalidResponse,
          'Lista de projetos: item invalido',
        );
      }
      projects.add(Map<String, dynamic>.from(item));
    }
    return projects;
  }

  Future<Job> createProject(String name, {String resourceProfile = 'medium'}) async {
    final body = generated.NewProject(
      name: name,
      resourceProfile: switch (resourceProfile) {
        'small' => generated.NewProjectResourceProfileEnum.small,
        'medium' => generated.NewProjectResourceProfileEnum.medium,
        'large' => generated.NewProjectResourceProfileEnum.large,
        'custom' => generated.NewProjectResourceProfileEnum.custom,
        _ => throw ArgumentError.value(
            resourceProfile,
            'resourceProfile',
            'Use small, medium, large ou custom',
          ),
      },
    );
    final response = await _client.post(
      Uri.parse('/api/projects'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body.toJson()),
    );
    _ensureCommandSucceeded(response, allowedStatusCodes: const {202});
    return Job.fromResponse(response);
  }

  Future<Job> duplicateProject(
    String originalName,
    String newName,
    bool copyData, {
    String? resourceProfile,
  }) async {
    final body = generated.DuplicateProject(
      originalName: originalName,
      newName: newName,
      copyData: copyData,
      resourceProfile: switch (resourceProfile) {
        null => null,
        'small' => generated.DuplicateProjectResourceProfileEnum.small,
        'medium' => generated.DuplicateProjectResourceProfileEnum.medium,
        'large' => generated.DuplicateProjectResourceProfileEnum.large,
        'custom' => generated.DuplicateProjectResourceProfileEnum.custom,
        _ => throw ArgumentError.value(
            resourceProfile,
            'resourceProfile',
            'Use small, medium, large ou custom',
          ),
      },
    );
    final response = await _client.post(
      Uri.parse('/api/projects/duplicate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body.toJson()),
    );
    _ensureCommandSucceeded(response, allowedStatusCodes: const {202});
    return Job.fromResponse(response);
  }

  Future<String> fetchProjectStatus(String ref) async {
    final response = await _client.get(Uri.parse('/api/projects/$ref/status'));
    _ensureCommandSucceeded(response);
    final decoded = decodeJsonObject(
      response,
      context: 'Status do projeto',
    );
    if (decoded['status'] is! String) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta de status invalida',
      );
    }
    return decoded['status'] as String;
  }

  Future<dynamic> getFullStatus(String ref) async {
    final resp = await _client.get(Uri.parse('/api/projects/$ref/status'));
    _ensureCommandSucceeded(resp);
    return decodeJsonResponse(resp, context: 'Status completo do projeto');
  }

  Future<List<dynamic>> getMembers(String ref) async {
    final resp = await _client.get(Uri.parse('/api/projects/$ref/members'));
    _ensureCommandSucceeded(resp);
    final data = decodeJsonResponse(resp, context: 'Membros do projeto');
    if (data is List) return data;
    if (data is Map && data['members'] is List) {
      return data['members'] as List<dynamic>;
    }
    throw const ApiException(
      ApiFailureKind.invalidResponse,
      'Resposta invalida ao carregar membros',
    );
  }

  Future<void> addMember(String ref, String userId, String role) async {
    final body = generated.AddMember(
      userId: userId,
      role: switch (role) {
        'admin' => generated.AddMemberRoleEnum.admin,
        'member' => generated.AddMemberRoleEnum.member,
        _ => throw ArgumentError.value(role, 'role', 'Use admin ou member'),
      },
    );
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/members'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body.toJson()),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> removeMember(String ref, String userId) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/members/$userId'),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<List<dynamic>> getAvailableUsers(String ref) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/available-users'),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonResponse(
      resp,
      context: 'Usuarios disponiveis do projeto',
    );
    if (data is List) return data;
    if (data is Map && data['users'] is List) {
      return data['users'] as List<dynamic>;
    }
    throw const ApiException(
      ApiFailureKind.invalidResponse,
      'Resposta invalida ao carregar usuarios',
    );
  }

  Future<List<dynamic>> getTransferAvailableUsers(
    String ref, {
    String mode = 'owner',
  }) async {
    final resp = await _client.get(
      Uri.parse(
        '/api/projects/$ref/available-users?include_members=true&mode=$mode',
      ),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonResponse(
      resp,
      context: 'Usuarios transferiveis do projeto',
    );
    if (data is List) return data;
    if (data is Map && data['users'] is List) {
      return data['users'] as List<dynamic>;
    }
    throw const ApiException(
      ApiFailureKind.invalidResponse,
      'Resposta invalida ao carregar usuarios para transferencia',
    );
  }

  Future<Map<String, dynamic>> updateAutomaticKeyRotation(
    String ref, {
    required bool enabled,
  }) async {
    final resp = await _client.put(
      Uri.parse('/api/projects/$ref/automatic-key-rotation'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.AutomaticKeyRotationUpdate(enabled: enabled).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(
      resp,
      context: 'Rotacao automatica de chaves',
    );
    if (data['automatic_key_rotation_enabled'] is! bool ||
        data['automatic_key_rotation_blocked'] is! bool) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao configurar rotacao automatica',
      );
    }
    return data;
  }

  Future<List<OpaqueApiKeySlot>> fetchOpaqueApiKeySlots(String ref) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/api-key-slots'),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(resp, context: 'Slots de API keys');
    final rawSlots = data['slots'];
    if (rawSlots is! List) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta sem lista de slots de API keys',
      );
    }
    return rawSlots
        .map(
          (item) => OpaqueApiKeySlot.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList();
  }

  Future<IssuedOpaqueApiKey> createOpaqueApiKeySlot(
    String ref, {
    required String name,
    required String kind,
    required List<String> allowedServices,
    required bool automaticRotationEnabled,
    required int? rotationIntervalDays,
    String? stepUpToken,
  }) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/api-key-slots'),
      headers: {
        'Content-Type': 'application/json',
        if (stepUpToken != null) 'X-Step-Up-Token': stepUpToken,
      },
      body: jsonEncode(
        generated.CreateApiKeySlot(
          name: name,
          kind: switch (kind) {
            'publishable' => generated.CreateApiKeySlotKindEnum.publishable,
            'secret' => generated.CreateApiKeySlotKindEnum.secret,
            _ => throw ArgumentError.value(
              kind,
              'kind',
              'Use publishable ou secret',
            ),
          },
          allowedServices: allowedServices,
          automaticRotationEnabled: automaticRotationEnabled,
          rotationIntervalDays: rotationIntervalDays,
        ).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {201});
    return IssuedOpaqueApiKey.fromJson(
      decodeJsonObject(resp, context: 'Nova API key'),
    );
  }

  Future<IssuedOpaqueApiKey> rotateOpaqueApiKeySlot(
    String ref,
    String slotId, {
    DateTime? activateAt,
    String? stepUpToken,
  }) async {
    final rotationBody = generated.RotateApiKeySlot(
      activateAt: activateAt,
    ).toJson();
    if (activateAt == null) {
      rotationBody.remove('activate_at');
    }
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/api-key-slots/$slotId/rotation'),
      headers: {
        'Content-Type': 'application/json',
        if (stepUpToken != null) 'X-Step-Up-Token': stepUpToken,
      },
      body: jsonEncode(rotationBody),
    );
    _ensureCommandSucceeded(resp);
    return IssuedOpaqueApiKey.fromJson(
      decodeJsonObject(resp, context: 'Rotacao de API key'),
    );
  }

  Future<void> updateOpaqueApiKeySlot(
    String ref,
    String slotId, {
    bool? automaticRotationEnabled,
    OpaqueApiKeyExpirationPolicyUpdate? expirationPolicy,
    List<String>? allowedServices,
    String? stepUpToken,
  }) async {
    final slotPolicyBody = generated.UpdateApiKeySlotPolicy(
      automaticRotationEnabled: automaticRotationEnabled,
      rotationIntervalDays: expirationPolicy?.rotationIntervalDays,
      allowedServices: allowedServices,
    ).toJson();
    if (automaticRotationEnabled == null) {
      slotPolicyBody.remove('automatic_rotation_enabled');
    }
    if (expirationPolicy == null) {
      slotPolicyBody.remove('rotation_interval_days');
    }
    if (allowedServices == null) {
      slotPolicyBody.remove('allowed_services');
    }
    final resp = await _client.patch(
      Uri.parse('/api/projects/$ref/api-key-slots/$slotId'),
      headers: {
        'Content-Type': 'application/json',
        if (stepUpToken != null) 'X-Step-Up-Token': stepUpToken,
      },
      body: jsonEncode(slotPolicyBody),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> disableOpaqueApiKeySlot(
    String ref,
    String slotId, {
    String? stepUpToken,
  }) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/api-key-slots/$slotId'),
      headers: {
        if (stepUpToken != null) 'X-Step-Up-Token': stepUpToken,
      },
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> cancelOpaqueApiKeyRotation(
    String ref,
    String slotId, {
    String? stepUpToken,
  }) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/api-key-slots/$slotId/rotation'),
      headers: {
        if (stepUpToken != null) 'X-Step-Up-Token': stepUpToken,
      },
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> confirmOpaqueApiKeyInstallation(
    String ref,
    String slotId,
    String keyId,
  ) async {
    final resp = await _client.post(
      Uri.parse(
        '/api/projects/$ref/api-key-slots/$slotId/rotation-confirmation',
      ),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ConfirmApiKeyInstallation(keyId: keyId).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<List<OpaqueApiKeyReveal>> fetchOpaqueApiKeyReveals(
    String ref,
  ) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/api-key-reveals'),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(resp, context: 'Revelacoes de API keys');
    final rawReveals = data['reveals'];
    if (rawReveals is! List) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta sem lista de revelacoes',
      );
    }
    return rawReveals
        .map(
          (item) => OpaqueApiKeyReveal.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList();
  }

  Future<String> claimOpaqueApiKey(
    String ref,
    String keyId, {
    String? stepUpToken,
  }) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/api-key-reveals/$keyId/claim'),
      headers: {
        if (stepUpToken != null) 'X-Step-Up-Token': stepUpToken,
      },
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(resp, context: 'Revelacao de API key');
    final apiKey = data['api_key'];
    if (apiKey is! String || apiKey.isEmpty) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta sem API key revelada',
      );
    }
    return apiKey;
  }

  Future<Map<String, dynamic>> fetchOpaqueApiKeyMigration(String ref) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/opaque-api-keys/migration'),
    );
    _ensureCommandSucceeded(resp);
    return decodeJsonObject(resp, context: 'Migracao de API keys opacas');
  }

  Future<Map<String, dynamic>> prepareOpaqueApiKeyMigration(String ref) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/opaque-api-keys/migration/prepare'),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {201});
    return decodeJsonObject(resp, context: 'Preparacao da migracao opaca');
  }

  Future<Map<String, dynamic>> abortOpaqueApiKeyMigration(String ref) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/opaque-api-keys/migration'),
    );
    _ensureCommandSucceeded(resp);
    return decodeJsonObject(resp, context: 'Cancelamento da migracao opaca');
  }

  Future<Map<String, dynamic>> cutoverOpaqueApiKeyMigration(String ref) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/opaque-api-keys/migration/cutover'),
    );
    _ensureCommandSucceeded(resp);
    return decodeJsonObject(resp, context: 'Corte da migracao opaca');
  }

  Future<ProjectActionResult> doAction(String ref, String action) async {
    final resp = await _client.post(Uri.parse('/api/projects/$ref/$action'));
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {200, 202});
    return ProjectActionResult(
      message: _extractMessage(resp),
      job: Job.fromOptionalResponse(resp),
    );
  }

  Future<void> transferProject(String ref, String newOwnerId) async {
    final resp = await _client.post(
      Uri.parse('/api/admin/projects/$ref/transfer'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.TransferBody(newOwnerId: newOwnerId).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<UserListResponse> fetchAdminUsers() async {
    final response = await _client.get(Uri.parse('/api/admin/users'));
    _ensureCommandSucceeded(response);
    if (response.body.isEmpty) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta vazia ao carregar usuarios',
      );
    }

    final data = decodeJsonObject(
      response,
      context: 'Usuarios administrativos',
    );

    final resp = UserListResponse.fromJson(data);

    if (resp.users.isNotEmpty) {
      final session = Session();
      resp.users.sort((a, b) {
        if ((a.userUuid ?? a.id) == session.myId) return -1;
        if ((b.userUuid ?? b.id) == session.myId) return 1;
        return 0;
      });
    }

    return resp;
  }

  Future<List<Map<String, dynamic>>> fetchAdminProjectsInfo(
    String userId,
  ) async {
    final response = await _client.post(
      Uri.parse('/api/admin/projects-info'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({'user_id': userId}),
    );
    _ensureCommandSucceeded(response);
    final decoded = decodeJsonObject(
      response,
      context: 'Projetos do usuario',
    );
    if (decoded['projects'] is! List) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao carregar projetos do usuario',
      );
    }
    return (decoded['projects'] as List<dynamic>)
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
  }

  Future<void> toggleUserStatus(String userId, bool isCurrentlyActive) async {
    final endpoint = isCurrentlyActive ? 'deactivate' : 'activate';
    final response = await _client.post(
      Uri.parse('/api/admin/users/$userId/$endpoint'),
      headers: {'Content-Type': 'application/json'},
    );

    _ensureCommandSucceeded(response);
  }

  Future<ProjectSettingsData> fetchProjectSettings(String ref) async {
    final resp = await _client.get(Uri.parse('/api/projects/$ref/settings'));
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(
      resp,
      context: 'Configuracoes do projeto',
    );
    if (data['settings'] is! Map) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao carregar configuracoes',
      );
    }
    final raw = Map<String, dynamic>.from(data['settings'] as Map);
    final pending = data['pending_affected_services'];
    if (pending != null && pending is! List) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Servicos pendentes invalidos',
      );
    }
    return ProjectSettingsData(
      settings: raw.map((key, value) => MapEntry(key, value.toString())),
      pendingAffectedServices: (pending as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      storageLimitToken: data['storage_limit_token']?.toString(),
    );
  }

  Future<String> fetchProjectConfigToken(String ref) async {
    final resp =
        await _client.get(Uri.parse('/api/projects/$ref/config-token'));
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(resp, context: 'Token do projeto');
    final token = data['config_token']?.toString() ?? '';
    if (token.isEmpty) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta sem config token',
      );
    }
    return token;
  }

  Future<ProjectUserTelemetry> fetchProjectUserTelemetry(
    String ref, {
    required String period,
    DateTime? start,
    DateTime? end,
  }) async {
    final query = <String, String>{
      'period': period,
      if (start != null) 'start': start.toUtc().toIso8601String(),
      if (end != null) 'end': end.toUtc().toIso8601String(),
    };
    final uri = Uri(
      path: '/api/projects/$ref/telemetry/users',
      queryParameters: query,
    );
    final resp = await _client.get(uri);
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(resp, context: 'Telemetria do projeto');
    return ProjectUserTelemetry.fromJson(data);
  }

  Future<UpdateSettingsResult> updateProjectSettings(
    String ref,
    Map<String, String> settings,
  ) async {
    final resp = await _client.put(
      Uri.parse('/api/projects/$ref/settings'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.UpdateSettings(settings: settings).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(
      resp,
      context: 'Atualizacao das configuracoes do projeto',
    );
    if (data['affected_services'] is! List) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao atualizar configuracoes',
      );
    }
    final raw = data['affected_services'] as List<dynamic>;
    return UpdateSettingsResult(
      affectedServices: raw.map((item) => item.toString()).toList(),
      storageLimitToken: data['storage_limit_token']?.toString(),
    );
  }

  Future<ProjectActionResult> recreateServices(
    String ref,
    List<String> services,
  ) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/recreate-services'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.RecreateServices(services: services).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {200, 202});
    return ProjectActionResult(
      message: _extractMessage(resp),
      job: Job.fromOptionalResponse(resp),
    );
  }

  Future<ProjectCollaboration> fetchProjectCollaboration(String ref) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/collaboration'),
    );
    _ensureCommandSucceeded(resp);
    return ProjectCollaboration.fromJson(
      decodeJsonObject(resp, context: 'Colaboracao do projeto'),
    );
  }

  Future<void> createProjectNote(
    String ref, {
    required String body,
    required String visibility,
  }) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/notes'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ProjectNoteCreate(body: body, visibility: visibility)
            .toJson(),
      ),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {201});
  }

  Future<void> deleteProjectNote(String ref, String noteId) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/notes/$noteId'),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> assignProjectTag(
    String ref, {
    String? tagId,
    String? name,
    String? color,
  }) async {
    final payload = generated.ProjectTagAssign(
      tagId: tagId,
      name: name,
      color: color,
    ).toJson();
    if (tagId == null) {
      payload.remove('tag_id');
    }
    if (name == null) {
      payload.remove('name');
    }
    if (color == null) {
      payload.remove('color');
    }
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/tags'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {201});
  }

  Future<void> removeProjectTag(String ref, String tagId) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/tags/$tagId'),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> createProjectHint(
    String ref, {
    required String targetUserId,
    required String body,
  }) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/hints'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ProjectHintCreate(targetUserId: targetUserId, body: body)
            .toJson(),
      ),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {201});
  }

  Future<void> updateProjectHintStatus(
    String ref,
    String hintId,
    String status,
  ) async {
    final resp = await _client.put(
      Uri.parse('/api/projects/$ref/hints/$hintId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ProjectHintStatusUpdate(status: status).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<void> createProjectThreadMessage(
    String ref, {
    required String body,
  }) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/thread/messages'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ProjectThreadMessageCreate(body: body).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {201});
  }

  Future<void> updateProjectNotificationReadState(
    String ref,
    String notificationId, {
    required bool read,
  }) async {
    final resp = await _client.patch(
      Uri.parse('/api/projects/$ref/notifications/$notificationId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ProjectNotificationRead(read: read).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<Job> renameProject(
    String ref, {
    required String newName,
    String? displayName,
  }) async {
    final payload = generated.ProjectRenameRequest(
      newName: newName,
      displayName: displayName,
    ).toJson();
    if (displayName == null) {
      payload.remove('display_name');
    }
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/rename'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {202});
    final job = Job.fromResponse(resp);
    return job;
  }

  Future<String> updateProjectDisplayName(
    String ref,
    String displayName,
  ) async {
    final resp = await _client.patch(
      Uri.parse('/api/projects/$ref/display-name'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(
        generated.ProjectDisplayNameUpdate(displayName: displayName).toJson(),
      ),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(resp, context: 'Nome de exibicao do projeto');
    if (data['display_name'] is! String) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta sem display_name',
      );
    }
    return data['display_name'] as String;
  }

  Future<RestorePointList> fetchRestorePoints(String ref) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/restore-points'),
    );
    _ensureCommandSucceeded(resp);
    final decoded = decodeJsonObject(
      resp,
      context: 'Pontos de restauracao',
    );
    if (decoded['points'] is! List ||
        decoded['permissions'] is! Map ||
        decoded['limit'] is! num) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao carregar pontos de restauracao',
      );
    }
    final data = Map<String, dynamic>.from(decoded);
    final raw = data['points'] as List<dynamic>;
    final permissions = Map<String, dynamic>.from(data['permissions'] as Map);
    return RestorePointList(
      limit: (data['limit'] as num).toInt(),
      canCreate: permissions['can_create'] == true,
      canRestore: permissions['can_restore'] == true,
      canDelete: permissions['can_delete'] == true,
      points: raw
          .map(
            (item) => RestorePoint.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
    );
  }

  Future<Job> createRestorePoint(
    String ref, {
    String? title,
    String? description,
  }) async {
    final restoreTitle =
        title != null && title.trim().isNotEmpty ? title.trim() : null;
    final restoreDescription =
        description != null && description.trim().isNotEmpty
            ? description.trim()
            : null;
    final restorePointBody = generated.RestorePointCreate(
      title: restoreTitle,
      description: restoreDescription,
    ).toJson();
    if (restoreTitle == null) {
      restorePointBody.remove('title');
    }
    if (restoreDescription == null) {
      restorePointBody.remove('description');
    }
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/restore-points'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(restorePointBody),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {202});
    final job = Job.fromResponse(resp);
    return job;
  }

  Future<Job> restoreRestorePoint(String ref, String pointId) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/restore-points/$pointId/restore'),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {202});
    final job = Job.fromResponse(resp);
    return job;
  }

  Future<Job> deleteRestorePoint(String ref, String pointId) async {
    final resp = await _client.delete(
      Uri.parse('/api/projects/$ref/restore-points/$pointId'),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {202});
    final job = Job.fromResponse(resp);
    return job;
  }

  Future<List<ProjectRenameEvent>> fetchProjectRenameHistory(String ref) async {
    final resp = await _client.get(
      Uri.parse('/api/projects/$ref/rename-history'),
    );
    _ensureCommandSucceeded(resp);
    final data = decodeJsonObject(
      resp,
      context: 'Historico de nomes do projeto',
    );
    if (data['events'] is! List) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao carregar historico de nomes',
      );
    }
    return (data['events'] as List<dynamic>)
        .map(
          (item) => ProjectRenameEvent.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList();
  }
}
