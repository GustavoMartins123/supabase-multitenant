import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../models/job.dart';
import 'api_client.dart';

final jobRepositoryProvider = Provider<JobRepository>((ref) {
  final repository = JobRepository();
  ref.onDispose(repository.close);
  return repository;
});

class JobSnapshot {
  const JobSnapshot(this.jobs, this.cursor);
  final List<Job> jobs;
  final String cursor;
}

class JobRepository {
  JobRepository({http.Client? client, Duration? timeout})
      : _client = ApiClient(client: client,
          timeout: timeout ?? const Duration(seconds: 35));
  final ApiClient _client;
  void close() => _client.close();

  Future<JobSnapshot> watch({String? cursor,
    Set<String> watchedIds = const {}, RequestCancellation? cancellation}) async {
    if (watchedIds.length > 200) {
      throw const FormatException('Limite de jobs acompanhados excedido');
    }
    final response = await _client.get(
      Uri(path: '/api/jobs/watch', queryParameters: {
        if (cursor != null) 'cursor': cursor,
        if (watchedIds.isNotEmpty) 'job_id': watchedIds.toList()..sort(),
      }), cancellation: cancellation);
    if (response.statusCode != 200) throw ApiException.fromResponse(response);
    final decoded = decodeJsonObject(response, context: 'Acompanhamento de jobs');
    final nextCursor = decoded['cursor'];
    if (decoded['items'] is! List || nextCursor is! String ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(nextCursor)) {
      throw const FormatException('Snapshot de jobs invalido');
    }
    final jobs = <Job>[];
    final ids = <String>{};
    for (final raw in decoded['items'] as List) {
      if (raw is! Map) throw const FormatException('Job invalido');
      final job = Job.fromJson(Map<String, dynamic>.from(raw));
      if (!ids.add(job.id)) throw const FormatException('Job duplicado');
      jobs.add(job);
    }
    if (!watchedIds.every(ids.contains)) {
      throw const FormatException('Snapshot nao contem todos os jobs acompanhados');
    }
    return JobSnapshot(jobs, nextCursor);
  }
}
