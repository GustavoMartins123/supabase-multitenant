import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/job.dart';
import '../models/user_models.dart';
import '../session.dart';

final projectRepositoryProvider = Provider((ref) => ProjectRepository());

class ProjectActionResult {
  const ProjectActionResult({this.message, this.job});

  final String? message;
  final Job? job;
}

class ProjectRepository {
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
    String? errorMessage;

    try {
      final data = _tryDecodeObject(resp.body);
      if (data != null) {
        final errors = data['errors'];
        final detail = data['detail'];
        final message = data['message'];

        if (errors is List && errors.isNotEmpty) {
          errorMessage = errors.join('\n');
        } else if (detail != null && detail.toString().isNotEmpty) {
          errorMessage = detail.toString();
        } else if (message != null && message.toString().isNotEmpty) {
          errorMessage = message.toString();
        }
      }
    } on FormatException {
      errorMessage = null;
    }

    throw Exception(
      errorMessage ??
          (resp.body.isEmpty ? 'HTTP ${resp.statusCode}' : resp.body),
    );
  }

  void _ensureCommandSucceeded(
    http.Response resp, {
    Set<int> allowedStatusCodes = const {200},
  }) {
    if (!allowedStatusCodes.contains(resp.statusCode)) {
      _throwParsedError(resp);
    }

    if (resp.body.isEmpty) return;

    try {
      final data = _tryDecodeObject(resp.body);
      if (data != null) {
        final success = data['success'];
        final errors = data['errors'];

        if (success == false || (errors is List && errors.isNotEmpty)) {
          _throwParsedError(resp);
        }
      }
    } on FormatException {
      return;
    }
  }

  Future<Map<String, dynamic>?> fetchConfig() async {
    try {
      final r = await http.get(Uri.parse('/api/config'));
      if (r.statusCode == 200) {
        return jsonDecode(r.body);
      }
    } catch (_) {}
    return null;
  }

  Future<List<Map<String, dynamic>>> fetchProjects() async {
    try {
      final r = await http.get(Uri.parse('/api/projects'));
      if (r.statusCode == 200) {
        final raw = jsonDecode(r.body) as List;
        return raw.map((e) => Map<String, dynamic>.from(e)).toList();
      }
    } catch (_) {}
    return [];
  }

  Future<Job?> createProject(String name) async {
    try {
      final res = await http.post(
        Uri.parse('/api/projects'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'name': name}),
      );
      return Job.fromResponse(res);
    } catch (_) {}
    return null;
  }

  Future<Job?> duplicateProject(
    String originalName,
    String newName,
    bool copyData,
  ) async {
    try {
      final res = await http.post(
        Uri.parse('/api/projects/duplicate'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'original_name': originalName,
          'new_name': newName,
          'copy_data': copyData,
        }),
      );
      return Job.fromResponse(res);
    } catch (_) {}
    return null;
  }

  Future<String?> fetchProjectStatus(String ref) async {
    try {
      final resp = await http.get(Uri.parse('/api/projects/$ref/status'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        return data['status'];
      }
    } catch (_) {}
    return null;
  }

  Future<dynamic> getFullStatus(String ref) async {
    final resp = await http.get(Uri.parse('/api/projects/$ref/status'));
    if (resp.statusCode == 200) {
      return jsonDecode(resp.body);
    }
    throw Exception('Erro ao carregar status: ${resp.body}');
  }

  Future<List<dynamic>> getMembers(String ref) async {
    final resp = await http.get(Uri.parse('/api/projects/$ref/members'));
    if (resp.statusCode == 200) {
      if (resp.body.isEmpty) return [];
      final dynamic data = jsonDecode(resp.body);
      if (data is List) return data;
      if (data is Map) {
        if (data.containsKey('members'))
          return data['members'] as List<dynamic>;
        if (data.containsKey('users')) return data['users'] as List<dynamic>;
      }
      return [];
    }
    throw Exception('Erro ao carregar membros: ${resp.body}');
  }

  Future<void> addMember(String ref, String userId, String role) async {
    final resp = await http.post(
      Uri.parse('/api/projects/$ref/members'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'user_id': userId, 'role': role}),
    );
    if (resp.statusCode != 200) {
      throw Exception('Erro ao adicionar membro: ${resp.body}');
    }
  }

  Future<void> removeMember(String ref, String userId) async {
    final resp = await http.delete(
      Uri.parse('/api/projects/$ref/members/$userId'),
    );
    if (resp.statusCode != 200) {
      throw Exception('Erro ao remover membro: ${resp.body}');
    }
  }

  Future<List<dynamic>> getAvailableUsers(String ref) async {
    final resp = await http.get(
      Uri.parse('/api/projects/$ref/available-users'),
    );
    if (resp.statusCode == 200) {
      if (resp.body.isEmpty) return [];
      final dynamic data = jsonDecode(resp.body);
      if (data is List) return data;
      if (data is Map && data.containsKey('users')) {
        return data['users'] as List<dynamic>;
      }
      return [];
    }
    throw Exception('Erro ao carregar usuários: ${resp.body}');
  }

  Future<List<dynamic>> getTransferAvailableUsers(
    String ref, {
    String mode = 'owner',
  }) async {
    final resp = await http.get(
      Uri.parse(
        '/api/projects/$ref/available-users?include_members=true&mode=$mode',
      ),
    );
    if (resp.statusCode == 200) {
      if (resp.body.isEmpty) return [];
      final dynamic data = jsonDecode(resp.body);
      if (data is List) return data;
      if (data is Map && data.containsKey('users')) {
        return data['users'] as List<dynamic>;
      }
      return [];
    }
    throw Exception(
      'Erro ao carregar usuários para transferência: ${resp.body}',
    );
  }

  Future<Map<String, dynamic>> rotateKey(String ref) async {
    final resp = await http.post(Uri.parse('/api/projects/$ref/rotate-key'));
    if (resp.statusCode == 200) {
      return jsonDecode(resp.body);
    }
    throw Exception('Erro ao rotacionar chave: ${resp.body}');
  }

  Future<ProjectActionResult> doAction(String ref, String action) async {
    final resp = await http.post(Uri.parse('/api/projects/$ref/$action'));
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {200, 202});
    return ProjectActionResult(
      message: _extractMessage(resp),
      job: Job.fromResponse(resp),
    );
  }

  Future<void> transferProject(String ref, String newOwnerId) async {
    final resp = await http.post(
      Uri.parse('/api/admin/projects/$ref/transfer'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'new_owner_id': newOwnerId}),
    );
    if (resp.statusCode != 200) {
      try {
        final err = jsonDecode(resp.body)['detail'] ?? resp.body;
        throw Exception(err);
      } catch (_) {
        throw Exception(resp.body);
      }
    }
  }

  Future<UserListResponse> fetchAdminUsers() async {
    final response = await http.get(Uri.parse('/api/admin/users'));

    if (response.statusCode == 403) {
      throw Exception('Acesso negado - apenas administradores');
    }

    if (response.statusCode != 200) {
      throw Exception('Erro ${response.statusCode}: ${response.body}');
    }

    if (response.body.isEmpty) {
      throw Exception('Resposta vazia da API');
    }

    final data = jsonDecode(response.body);
    if (data == null) {
      throw Exception('Dados inválidos retornados pela API');
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

  Future<void> toggleUserStatus(String userId, bool isCurrentlyActive) async {
    final endpoint = isCurrentlyActive ? 'deactivate' : 'activate';
    final response = await http.post(
      Uri.parse('/api/admin/users/$userId/$endpoint'),
      headers: {'Content-Type': 'application/json'},
    );

    if (response.statusCode != 200) {
      final error = jsonDecode(response.body)['error'] ?? 'Erro desconhecido';
      throw Exception(error);
    }
  }

  Future<Map<String, String>> fetchProjectSettings(String ref) async {
    final resp = await http.get(Uri.parse('/api/projects/$ref/settings'));
    if (resp.statusCode == 200) {
      final data = jsonDecode(resp.body);
      final raw = data['settings'] as Map<String, dynamic>;
      return raw.map((k, v) => MapEntry(k, v.toString()));
    }
    if (resp.statusCode == 403) {
      throw Exception('Acesso negado');
    }
    throw Exception('Erro ao carregar settings: ${resp.body}');
  }

  Future<List<String>> updateProjectSettings(
    String ref,
    Map<String, String> settings,
  ) async {
    final resp = await http.put(
      Uri.parse('/api/projects/$ref/settings'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'settings': settings}),
    );
    if (resp.statusCode == 200) {
      final data = jsonDecode(resp.body);
      final raw = data['affected_services'] as List<dynamic>? ?? [];
      return raw.map((e) => e.toString()).toList();
    }
    try {
      final err = jsonDecode(resp.body)['detail'] ?? resp.body;
      throw Exception(err);
    } catch (_) {
      throw Exception(resp.body);
    }
  }

  Future<ProjectActionResult> recreateServices(
    String ref,
    List<String> services,
  ) async {
    final resp = await http.post(
      Uri.parse('/api/projects/$ref/recreate-services'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'services': services}),
    );
    _ensureCommandSucceeded(resp, allowedStatusCodes: const {200, 202});
    return ProjectActionResult(
      message: _extractMessage(resp),
      job: Job.fromResponse(resp),
    );
  }
}
