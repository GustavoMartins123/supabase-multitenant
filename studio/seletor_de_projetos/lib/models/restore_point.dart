class RestorePoint {
  const RestorePoint({
    required this.id,
    required this.title,
    required this.status,
    required this.isAutomatic,
    required this.restoreCount,
    this.description,
    this.jobId,
    this.createdBy,
    this.createdByName,
    this.projectRefAtCreation,
    this.sizeBytes,
    this.lastRestoredAt,
    this.error,
    this.createdAt,
    this.completedAt,
  });

  final String id;
  final String title;
  final String? description;
  final String status;
  final bool isAutomatic;
  final String? jobId;
  final String? createdBy;
  final String? createdByName;
  final String? projectRefAtCreation;
  final int? sizeBytes;
  final DateTime? lastRestoredAt;
  final int restoreCount;
  final String? error;
  final DateTime? createdAt;
  final DateTime? completedAt;

  bool get isReady => status == 'ready';
  bool get isFailed => status == 'failed';
  bool get isBusy =>
      status == 'creating' || status == 'restoring' || status == 'deleting';

  static DateTime? _parseDate(dynamic value) {
    if (value is! String || value.isEmpty) return null;
    return DateTime.tryParse(value);
  }

  factory RestorePoint.fromJson(Map<String, dynamic> json) {
    return RestorePoint(
      id: json['id'] as String,
      title: json['title'] as String? ?? '',
      description: json['description'] as String?,
      status: json['status'] as String? ?? 'ready',
      isAutomatic: json['is_automatic'] == true,
      jobId: json['job_id'] as String?,
      createdBy: json['created_by'] as String?,
      createdByName: json['created_by_name'] as String?,
      projectRefAtCreation: json['project_ref_at_creation'] as String?,
      sizeBytes: (json['size_bytes'] as num?)?.toInt(),
      lastRestoredAt: _parseDate(json['last_restored_at']),
      restoreCount: (json['restore_count'] as num?)?.toInt() ?? 0,
      error: json['error'] as String?,
      createdAt: _parseDate(json['created_at']),
      completedAt: _parseDate(json['completed_at']),
    );
  }
}

class RestorePointList {
  const RestorePointList({required this.limit, required this.points});

  final int limit;
  final List<RestorePoint> points;

  int get activeCount => points.where((p) => !p.isFailed).length;
}
