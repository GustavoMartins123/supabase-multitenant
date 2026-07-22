import 'package:http/http.dart' as http;

import '../data/api_client.dart';

class Job {
  const Job(
    this.id, {
    this.project,
    this.projectUuid,
    this.tenantUuid,
    this.createdBy,
    this.action,
    required this.status,
    this.message,
    this.progress,
    this.currentStep,
    this.totalSteps,
    this.createdAt,
    this.updatedAt,
  });

  final String id;

  final String? project;
  final String? projectUuid;
  final String? tenantUuid;
  final String? createdBy;
  final String? action;
  final String status;
  final String? message;
  final int? progress;
  final String? currentStep;
  final int? totalSteps;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get isInFlight => status == 'queued' || status == 'running';

  factory Job.fromJson(Map<String, dynamic> json) {
    final id = json['job_id']?.toString();
    if (id == null || id.isEmpty) {
      throw const FormatException('Job sem job_id');
    }

    return Job(
      id,
      project: json['project']?.toString(),
      projectUuid: json['project_uuid']?.toString(),
      tenantUuid: json['tenant_uuid']?.toString(),
      createdBy: json['created_by']?.toString(),
      action: json['action']?.toString(),
      status: _requireText(json, 'status'),
      message: json['message']?.toString(),
      progress: (json['progress'] as num?)?.toInt(),
      currentStep: json['current_step']?.toString(),
      totalSteps: (json['total_steps'] as num?)?.toInt(),
      createdAt: _parseDate(json['created_at']),
      updatedAt: _parseDate(json['updated_at']),
    );
  }

  Job verifyContext({
    String? project,
    Iterable<String>? acceptedProjects,
    String? action,
    String? createdBy,
  }) {
    if (project != null && acceptedProjects != null) {
      throw ArgumentError(
        'Use project ou acceptedProjects, nunca os dois',
      );
    }
    final validProjects =
        project == null ? acceptedProjects?.toSet() : <String>{project};
    if (validProjects != null && !validProjects.contains(this.project)) {
      throw const FormatException(
        'Contrato do job invalido: project divergente ou ausente',
      );
    }
    final expected = {
      if (action != null) 'action': action,
      if (createdBy != null) 'created_by': createdBy,
    };
    final actual = {
      'action': this.action,
      'created_by': this.createdBy,
    };
    for (final entry in expected.entries) {
      if (actual[entry.key] != entry.value) {
        throw FormatException(
          'Contrato do job invalido: ${entry.key} divergente ou ausente',
        );
      }
    }
    return this;
  }

  static Job fromResponse(http.Response r) {
    if (r.statusCode != 202) {
      throw ApiException.fromResponse(r);
    }
    final decoded = decodeJsonObject(r, context: 'Criacao do job');
    if (decoded['job_id'] == null) {
      throw const FormatException('Resposta sem job_id');
    }
    return Job.fromJson(decoded);
  }

  static Job? fromOptionalResponse(http.Response response) {
    return response.statusCode == 202 ? fromResponse(response) : null;
  }

  static DateTime? _parseDate(Object? raw) {
    if (raw == null) return null;
    return DateTime.parse(raw.toString());
  }

  static String _requireText(Map<String, dynamic> json, String key) {
    final value = json[key]?.toString().trim();
    if (value == null || value.isEmpty) {
      throw FormatException('Job sem $key');
    }
    return value;
  }
}
