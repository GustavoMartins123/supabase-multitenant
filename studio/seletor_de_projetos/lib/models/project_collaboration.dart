class ProjectTag {
  const ProjectTag({
    required this.id,
    required this.name,
    required this.color,
    required this.category,
    required this.isSystem,
    required this.assigned,
  });

  final String id;
  final String name;
  final String color;
  final String category;
  final bool isSystem;
  final bool assigned;

  factory ProjectTag.fromJson(Map<String, dynamic> json) {
    return ProjectTag(
      id: json['id'].toString(),
      name: json['name'].toString(),
      color: json['color']?.toString() ?? '#3ECF8E',
      category: json['category']?.toString() ?? 'custom',
      isSystem: json['is_system'] == true,
      assigned: json['assigned'] == true,
    );
  }
}

class ProjectNote {
  const ProjectNote({
    required this.id,
    required this.visibility,
    required this.body,
    required this.authorName,
    required this.createdAt,
    required this.isEncrypted,
    required this.canDelete,
  });

  final String id;
  final String visibility;
  final String body;
  final String authorName;
  final DateTime createdAt;
  final bool isEncrypted;
  final bool canDelete;

  factory ProjectNote.fromJson(Map<String, dynamic> json) {
    return ProjectNote(
      id: json['id'].toString(),
      visibility: json['visibility']?.toString() ?? 'private',
      body: json['body']?.toString() ?? '',
      authorName: json['author_name']?.toString() ?? 'Operador',
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
      isEncrypted: json['is_encrypted'] == true,
      canDelete: json['can_delete'] == true,
    );
  }
}

class ProjectCollaborationMember {
  const ProjectCollaborationMember({
    required this.id,
    required this.displayName,
    required this.username,
    required this.role,
  });

  final String id;
  final String displayName;
  final String username;
  final String role;

  String get label => displayName.isNotEmpty ? displayName : username;

  factory ProjectCollaborationMember.fromJson(Map<String, dynamic> json) {
    return ProjectCollaborationMember(
      id: json['id'].toString(),
      displayName: json['display_name']?.toString() ?? '',
      username: json['username']?.toString() ?? '',
      role: json['role']?.toString() ?? 'member',
    );
  }
}

class ProjectHint {
  const ProjectHint({
    required this.id,
    required this.body,
    required this.status,
    required this.authorName,
    required this.targetName,
    required this.createdAt,
    required this.updatedAt,
    required this.canUpdate,
    this.resolvedAt,
    this.resolvedByName,
  });

  final String id;
  final String body;
  final String status;
  final String authorName;
  final String targetName;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;
  final String? resolvedByName;
  final bool canUpdate;

  bool get isOpen => status == 'open';

  factory ProjectHint.fromJson(Map<String, dynamic> json) {
    return ProjectHint(
      id: json['id'].toString(),
      body: json['body']?.toString() ?? '',
      status: json['status']?.toString() ?? 'open',
      authorName: json['author_name']?.toString() ?? 'Operador',
      targetName: json['target_name']?.toString() ?? 'Operador',
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at']?.toString() ?? '') ??
          DateTime.now(),
      resolvedAt: DateTime.tryParse(json['resolved_at']?.toString() ?? ''),
      resolvedByName: json['resolved_by_name']?.toString(),
      canUpdate: json['can_update'] == true,
    );
  }
}

class ProjectThreadMessage {
  const ProjectThreadMessage({
    required this.id,
    required this.body,
    required this.authorName,
    required this.createdAt,
  });

  final String id;
  final String body;
  final String authorName;
  final DateTime createdAt;

  factory ProjectThreadMessage.fromJson(Map<String, dynamic> json) {
    return ProjectThreadMessage(
      id: json['id'].toString(),
      body: json['body']?.toString() ?? '',
      authorName: json['author_name']?.toString() ?? 'Operador',
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
    );
  }
}

class ProjectNotification {
  const ProjectNotification({
    required this.id,
    required this.kind,
    required this.targetType,
    required this.actorName,
    required this.payload,
    required this.createdAt,
    this.targetId,
    this.readAt,
  });

  final String id;
  final String kind;
  final String targetType;
  final String? targetId;
  final String actorName;
  final Map<String, dynamic> payload;
  final DateTime createdAt;
  final DateTime? readAt;

  bool get isRead => readAt != null;

  String get label {
    switch (kind) {
      case 'project_hint_created':
        return 'Novo hint atribuido a voce';
      case 'project_thread_message_created':
        return 'Nova mensagem na thread';
      case 'project_renamed':
        return 'Projeto renomeado';
      default:
        return kind;
    }
  }

  factory ProjectNotification.fromJson(Map<String, dynamic> json) {
    return ProjectNotification(
      id: json['id'].toString(),
      kind: json['kind']?.toString() ?? '',
      targetType: json['target_type']?.toString() ?? '',
      targetId: json['target_id']?.toString(),
      actorName: json['actor_name']?.toString() ?? 'Sistema',
      payload: json['payload'] is Map
          ? Map<String, dynamic>.from(json['payload'] as Map)
          : const {},
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
      readAt: DateTime.tryParse(json['read_at']?.toString() ?? ''),
    );
  }
}

class ProjectCollaboration {
  const ProjectCollaboration({
    required this.project,
    required this.availableTags,
    required this.assignedTags,
    required this.members,
    required this.notes,
    required this.hints,
    required this.threadMessages,
    required this.notifications,
  });

  final String project;
  final List<ProjectTag> availableTags;
  final List<ProjectTag> assignedTags;
  final List<ProjectCollaborationMember> members;
  final List<ProjectNote> notes;
  final List<ProjectHint> hints;
  final List<ProjectThreadMessage> threadMessages;
  final List<ProjectNotification> notifications;

  factory ProjectCollaboration.fromJson(Map<String, dynamic> json) {
    final rawAvailable = json['available_tags'] as List<dynamic>? ?? [];
    final rawAssigned = json['assigned_tags'] as List<dynamic>? ?? [];
    final rawMembers = json['members'] as List<dynamic>? ?? [];
    final rawNotes = json['notes'] as List<dynamic>? ?? [];
    final rawHints = json['hints'] as List<dynamic>? ?? [];
    final rawThreadMessages = json['thread_messages'] as List<dynamic>? ?? [];
    final rawNotifications = json['notifications'] as List<dynamic>? ?? [];

    return ProjectCollaboration(
      project: json['project']?.toString() ?? '',
      availableTags: rawAvailable
          .map((e) => ProjectTag.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      assignedTags: rawAssigned
          .map((e) => ProjectTag.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      members: rawMembers
          .map(
            (e) => ProjectCollaborationMember.fromJson(
              Map<String, dynamic>.from(e as Map),
            ),
          )
          .toList(),
      notes: rawNotes
          .map((e) => ProjectNote.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      hints: rawHints
          .map((e) => ProjectHint.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      threadMessages: rawThreadMessages
          .map(
            (e) => ProjectThreadMessage.fromJson(
              Map<String, dynamic>.from(e as Map),
            ),
          )
          .toList(),
      notifications: rawNotifications
          .map(
            (e) => ProjectNotification.fromJson(
              Map<String, dynamic>.from(e as Map),
            ),
          )
          .toList(),
    );
  }
}

class ProjectRenameEvent {
  const ProjectRenameEvent({
    required this.id,
    required this.action,
    required this.actorName,
    required this.oldValue,
    required this.newValue,
    required this.targetId,
    required this.createdAt,
  });

  final String id;
  final String action;
  final String actorName;
  final Map<String, dynamic>? oldValue;
  final Map<String, dynamic>? newValue;
  final String? targetId;
  final DateTime createdAt;

  String get label {
    switch (action) {
      case 'project_rename_started':
        return 'Renomeação iniciada';
      case 'project_rename_succeeded':
        return 'Renomeação concluída';
      case 'project_rename_failed':
        return 'Falha na renomeação';
      case 'project_rename_rolled_back':
        return 'Renomeação revertida';
      case 'project_display_name_changed':
        return 'Nome de exibição alterado';
      default:
        return action;
    }
  }

  factory ProjectRenameEvent.fromJson(Map<String, dynamic> json) {
    return ProjectRenameEvent(
      id: json['id'].toString(),
      action: json['action']?.toString() ?? '',
      actorName: json['actor_name']?.toString() ?? 'Sistema',
      oldValue: json['old_value'] is Map
          ? Map<String, dynamic>.from(json['old_value'] as Map)
          : null,
      newValue: json['new_value'] is Map
          ? Map<String, dynamic>.from(json['new_value'] as Map)
          : null,
      targetId: json['target_id']?.toString(),
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
    );
  }
}
