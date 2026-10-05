import 'dart:convert';
import '../data/api_client.dart';
import '../models/access_policy.dart';

class AccessPolicyService {
  AccessPolicyService({ApiClient? client}) : _client = client ?? ApiClient();
  final ApiClient _client;
  void close() => _client.close();

  Uri uri(String project, String? slot) => Uri(
      path: slot == null
          ? '/api/projects/$project/access-policy'
          : '/api/projects/$project/api-key-slots/$slot/access-policy');

  AccessPolicySnapshot snapshot(Map<String, dynamic> json, String? slot) {
    final value = AccessPolicySnapshot.fromJson(json);
    if (value.scope != (slot == null ? 'project' : 'slot') ||
        (slot != null && value.scopeId != slot)) {
      throw const FormatException(
          'Identidade de política não corresponde ao recurso solicitado');
    }
    return value;
  }

  Future<AccessPolicySnapshot> get(String project, String? slot) async {
    final response = await _client.get(uri(project, slot));
    if (response.statusCode != 200) throw ApiException.fromResponse(response);
    return snapshot(
        decodeJsonObject(response, context: 'Política de acesso'), slot);
  }

  Future<List<AccessCountry>> countries() async {
    final response = await _client.get(Uri(path: '/api/projects/countries'));
    if (response.statusCode != 200) throw ApiException.fromResponse(response);
    final json = decodeJsonObject(response, context: 'Catálogo de países');
    if (json['countries'] is! List) {
      throw const FormatException('Catálogo inválido');
    }
    return (json['countries'] as List)
        .map((value) =>
            AccessCountry.fromJson(Map<String, dynamic>.from(value as Map)))
        .toList();
  }

  Future<AccessPolicySnapshot> save(String project, String? slot, int revision,
      Map<String, dynamic> policy, String? stepUp) async {
    final response = await _client.put(uri(project, slot),
        headers: {
          'Content-Type': 'application/json',
          if (stepUp != null) 'X-Step-Up-Token': stepUp
        },
        body: jsonEncode({'revision': revision, 'policy': policy}));
    if (response.statusCode != 200) throw ApiException.fromResponse(response);
    return snapshot(
        decodeJsonObject(response, context: 'Salvar política'), slot);
  }

  Future<List<Map<String, dynamic>>> usage(String project) async {
    final response =
        await _client.get(Uri(path: '/api/projects/$project/access-usage'));
    if (response.statusCode != 200) throw ApiException.fromResponse(response);
    final json = decodeJsonObject(response, context: 'Consumo');
    if (json['usage'] is! List) throw const FormatException('Consumo inválido');
    return (json['usage'] as List)
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList();
  }
}
