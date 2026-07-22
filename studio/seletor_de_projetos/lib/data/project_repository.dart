import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/job.dart';
import '../models/project_collaboration.dart';
import '../models/restore_point.dart';
import '../models/user_models.dart';
import '../models/project_user_telemetry.dart';
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
    if (body.isEmpty) return null;

    try {
      final data = jsonDecode(body);
      return data is Map<String, dynamic> ? data : null;
    } on FormatException {
      return null;
    }
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
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta invalida ao carregar configuracao',
      );
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<List<Map<String, dynamic>>> fetchProjects({
    RequestCancellation? cancellation,
  }) async {
    final response = await _client.get(
      Uri.parse('/api/projects'),
      cancellation: cancellation,
    );
    _ensureCommandSucceeded(response);
    final decoded = jsonDecode(response.body);
    if (decoded is! List) {
      throw const FormatException('Resposta inválida ao listar projetos');
    }
    return decoded
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
  }

  Future<Job> createProject(String name) async {
    final response = await _client.post(
      Uri.parse('/api/projects'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    _ensureCommandSucceeded(response, allowedStatusCodes: const {202});
    return Job.fromResponse(response);
  }

  Future<Job> duplicateProject(
    String originalName,
    String newName,
    bool copyData,
  ) async {
    final response = await _client.post(
      Uri.parse('/api/projects/duplicate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'original_name': originalName,
        'new_name': newName,
        'copy_data': copyData,
      }),
    );
    _ensureCommandSucceeded(response, allowedStatusCodes: const {202});
    return Job.fromResponse(response);
  }

  Future<String> fetchProjectStatus(String ref) async {
    final response = await _client.get(Uri.parse('/api/projects/$ref/status'));
    _ensureCommandSucceeded(response);
    final decoded = jsonDecode(response.body);
    if (decoded is! Map || decoded['status'] is! String) {
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
    return jsonDecode(resp.body);
  }

  Future<List<dynamic>> getMembers(String ref) async {
    final resp = await _client.get(Uri.parse('/api/projects/$ref/members'));
    _ensureCommandSucceeded(resp);
    final dynamic data = jsonDecode(resp.body);
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
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/members'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'user_id': userId, 'role': role}),
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
    final dynamic data = jsonDecode(resp.body);
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
    final dynamic data = jsonDecode(resp.body);
    if (data is List) return data;
    if (data is Map && data['users'] is List) {
      return data['users'] as List<dynamic>;
    }
    throw const ApiException(
      ApiFailureKind.invalidResponse,
      'Resposta invalida ao carregar usuarios para transferencia',
    );
  }

  Future<Job> rotateKey(String ref) async {
    final resp = await _client.post(Uri.parse('/api/projects/$ref/rotate-key'));
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {202});
    final job = Job.fromResponse(resp);
    return job;
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
      body: jsonEncode({'new_owner_id': newOwnerId}),
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

    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic>) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Dados invalidos ao carregar usuarios',
      );
    }

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
    final decoded = jsonDecode(response.body);
    if (decoded is! Map || decoded['projects'] is! List) {
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
    final data = jsonDecode(resp.body);
    if (data is! Map || data['settings'] is! Map) {
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
    final data = _tryDecodeObject(resp.body);
    final token = data?['config_token']?.toString() ?? '';
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
    final data = _tryDecodeObject(resp.body);
    if (data == null) {
      throw const ApiException(
        ApiFailureKind.invalidResponse,
        'Resposta de telemetria invalida',
      );
    }
    return ProjectUserTelemetry.fromJson(data);
  }

  Future<UpdateSettingsResult> updateProjectSettings(
    String ref,
    Map<String, String> settings,
  ) async {
    final resp = await _client.put(
      Uri.parse('/api/projects/$ref/settings'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'settings': settings}),
    );
    _ensureCommandSucceeded(resp);
    final data = jsonDecode(resp.body);
    if (data is! Map || data['affected_services'] is! List) {
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
      body: jsonEncode({'services': services}),
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
    return ProjectCollaboration.fromJson(jsonDecode(resp.body));
  }

  Future<void> createProjectNote(
    String ref, {
    required String body,
    required String visibility,
  }) async {
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/notes'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'body': body, 'visibility': visibility}),
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
    final payload = <String, dynamic>{
      if (tagId != null) 'tag_id': tagId,
      if (name != null) 'name': name,
      if (color != null) 'color': color,
    };
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
      body: jsonEncode({'target_user_id': targetUserId, 'body': body}),
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
      body: jsonEncode({'status': status}),
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
      body: jsonEncode({'body': body}),
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
      body: jsonEncode({'read': read}),
    );
    _ensureCommandSucceeded(resp);
  }

  Future<Job> renameProject(
    String ref, {
    required String newName,
    String? displayName,
  }) async {
    final payload = <String, dynamic>{
      'new_name': newName,
      if (displayName != null) 'display_name': displayName,
    };
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
      body: jsonEncode({'display_name': displayName}),
    );
    _ensureCommandSucceeded(resp);
    final data = _tryDecodeObject(resp.body);
    if (data == null || data['display_name'] is! String) {
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
    final decoded = jsonDecode(resp.body);
    if (decoded is! Map ||
        decoded['points'] is! List ||
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
    final resp = await _client.post(
      Uri.parse('/api/projects/$ref/restore-points'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        if (title != null && title.trim().isNotEmpty) 'title': title.trim(),
        if (description != null && description.trim().isNotEmpty)
          'description': description.trim(),
      }),
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
    final data = jsonDecode(resp.body);
    if (data is! Map || data['events'] is! List) {
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
