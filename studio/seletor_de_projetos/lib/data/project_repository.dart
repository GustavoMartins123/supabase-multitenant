import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/job.dart';

final projectRepositoryProvider = Provider((ref) => ProjectRepository());

class ProjectRepository {
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
      String originalName, String newName, bool copyData) async {
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
      return jsonDecode(resp.body);
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
    final resp =
        await http.delete(Uri.parse('/api/projects/$ref/members/$userId'));
    if (resp.statusCode != 200) {
      throw Exception('Erro ao remover membro: ${resp.body}');
    }
  }

  Future<List<dynamic>> getAvailableUsers(String ref) async {
    final resp =
        await http.get(Uri.parse('/api/projects/$ref/available-users'));
    if (resp.statusCode == 200) {
      return jsonDecode(resp.body);
    }
    throw Exception('Erro ao carregar usuários: ${resp.body}');
  }

  Future<Map<String, dynamic>> rotateKey(String ref) async {
    final resp = await http.post(Uri.parse('/api/projects/$ref/rotate-key'));
    if (resp.statusCode == 200) {
      return jsonDecode(resp.body);
    }
    throw Exception('Erro ao rotacionar chave: ${resp.body}');
  }

  Future<void> cacheBust(String ref) async {
    await http.get(Uri.parse('/api/internal/cache-bust?ref=$ref'));
  }

  Future<void> doAction(String ref, String action) async {
    final resp = await http.post(Uri.parse('/api/projects/$ref/$action'));
    if (resp.statusCode != 200) {
      final err = jsonDecode(resp.body)['detail'] ?? resp.body;
      throw Exception(err);
    }
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
}
