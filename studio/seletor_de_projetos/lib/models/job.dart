import 'dart:convert';

import 'package:http/http.dart' as http;

class Job {
  const Job(this.id);
  final String id;
  static Job? fromResponse(http.Response r) {
    if (r.statusCode != 202) return null;
    final js = jsonDecode(r.body);
    return js is Map && js['job_id'] is String ? Job(js['job_id']) : null;
  }
}