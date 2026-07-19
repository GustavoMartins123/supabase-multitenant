import 'dart:convert';

import 'package:http/http.dart' as http;

class Job {
  const Job(
    this.id, {
    this.project,
    this.projectUuid,
    this.createdBy,
    this.action,
    this.status = 'queued',
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
      createdBy: json['created_by']?.toString(),
      action: json['action']?.toString(),
      status: json['status']?.toString() ?? 'queued',
      message: json['message']?.toString(),
      progress: (json['progress'] as num?)?.toInt(),
      currentStep: json['current_step']?.toString(),
      totalSteps: (json['total_steps'] as num?)?.toInt(),
      createdAt: _parseDate(json['created_at']),
      updatedAt: _parseDate(json['updated_at']),
    );
  }

  Job withFallback({String? project, String? action, String? createdBy}) {
    return Job(
      id,
      project: this.project ?? project,
      projectUuid: projectUuid,
      createdBy: this.createdBy ?? createdBy,
      action: this.action ?? action,
      status: status,
      message: message,
      progress: progress,
      currentStep: currentStep,
      totalSteps: totalSteps,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }

  static Job? fromResponse(http.Response r) {
    if (r.statusCode != 202) return null;
    final decoded = jsonDecode(r.body);
    if (decoded is! Map || decoded['job_id'] == null) return null;
    return Job.fromJson(Map<String, dynamic>.from(decoded));
  }

  static DateTime? _parseDate(Object? raw) {
    if (raw == null) return null;
    return DateTime.tryParse(raw.toString());
  }
}
