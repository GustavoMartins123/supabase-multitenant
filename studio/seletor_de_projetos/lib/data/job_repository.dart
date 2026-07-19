import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../models/job.dart';

final jobRepositoryProvider = Provider<JobRepository>((ref) {
  final repository = JobRepository();
  ref.onDispose(repository.close);
  return repository;
});

class JobRepository {
  JobRepository({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  void close() => _client.close();

  Future<List<Job>> fetchInFlightJobs() async {
    final responses = await Future.wait(
      const ['queued', 'running'].map(
        (status) => _client.get(
          Uri(
            path: '/api/jobs',
            queryParameters: {'status': status, 'limit': '200'},
          ),
        ),
      ),
    );

    final jobs = <String, Job>{};
    for (final response in responses) {
      if (response.statusCode != 200) {
        throw Exception(
          'Erro ao consultar jobs (${response.statusCode}): ${response.body}',
        );
      }

      final decoded = jsonDecode(response.body);
      if (decoded is! Map || decoded['items'] is! List) {
        throw const FormatException('Resposta inválida ao consultar jobs');
      }

      for (final raw in decoded['items'] as List<dynamic>) {
        if (raw is! Map) continue;
        final job = Job.fromJson(Map<String, dynamic>.from(raw));
        if (job.isInFlight) jobs[job.id] = job;
      }
    }

    final result = jobs.values.toList();
    result.sort((a, b) {
      final aDate = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final bDate = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      return aDate.compareTo(bDate);
    });
    return result;
  }
}
