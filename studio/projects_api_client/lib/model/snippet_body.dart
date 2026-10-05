//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class SnippetBody {
  /// Returns a new [SnippetBody] instance.
  SnippetBody({
    required this.content,
    this.description,
    this.favorite = false,
    this.folderId,
    required this.id,
    this.insertedAt,
    required this.name,
    this.owner = const {},
    this.ownerId,
    this.ownerUuid,
    this.projectId,
    this.projectUuid,
    this.status,
    required this.type,
    this.updatedAt,
    this.updatedBy = const {},
    required this.visibility,
  });

  SqlContent content;

  String? description;

  bool favorite;

  String? folderId;

  String id;

  String? insertedAt;

  String name;

  Map<String, Object>? owner;

  OwnerId? ownerId;

  String? ownerUuid;

  ProjectId? projectId;

  String? projectUuid;

  String? status;

  String type;

  String? updatedAt;

  Map<String, Object>? updatedBy;

  String visibility;

  @override
  bool operator ==(Object other) => identical(this, other) || other is SnippetBody &&
    other.content == content &&
    other.description == description &&
    other.favorite == favorite &&
    other.folderId == folderId &&
    other.id == id &&
    other.insertedAt == insertedAt &&
    other.name == name &&
    _deepEquality.equals(other.owner, owner) &&
    other.ownerId == ownerId &&
    other.ownerUuid == ownerUuid &&
    other.projectId == projectId &&
    other.projectUuid == projectUuid &&
    other.status == status &&
    other.type == type &&
    other.updatedAt == updatedAt &&
    _deepEquality.equals(other.updatedBy, updatedBy) &&
    other.visibility == visibility;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (content.hashCode) +
    (description == null ? 0 : description!.hashCode) +
    (favorite.hashCode) +
    (folderId == null ? 0 : folderId!.hashCode) +
    (id.hashCode) +
    (insertedAt == null ? 0 : insertedAt!.hashCode) +
    (name.hashCode) +
    (owner == null ? 0 : owner!.hashCode) +
    (ownerId == null ? 0 : ownerId!.hashCode) +
    (ownerUuid == null ? 0 : ownerUuid!.hashCode) +
    (projectId == null ? 0 : projectId!.hashCode) +
    (projectUuid == null ? 0 : projectUuid!.hashCode) +
    (status == null ? 0 : status!.hashCode) +
    (type.hashCode) +
    (updatedAt == null ? 0 : updatedAt!.hashCode) +
    (updatedBy == null ? 0 : updatedBy!.hashCode) +
    (visibility.hashCode);

  @override
  String toString() => 'SnippetBody[content=$content, description=$description, favorite=$favorite, folderId=$folderId, id=$id, insertedAt=$insertedAt, name=$name, owner=$owner, ownerId=$ownerId, ownerUuid=$ownerUuid, projectId=$projectId, projectUuid=$projectUuid, status=$status, type=$type, updatedAt=$updatedAt, updatedBy=$updatedBy, visibility=$visibility]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'content'] = this.content;
    if (this.description != null) {
      json[r'description'] = this.description;
    } else {
      json[r'description'] = null;
    }
      json[r'favorite'] = this.favorite;
    if (this.folderId != null) {
      json[r'folder_id'] = this.folderId;
    } else {
      json[r'folder_id'] = null;
    }
      json[r'id'] = this.id;
    if (this.insertedAt != null) {
      json[r'inserted_at'] = this.insertedAt;
    } else {
      json[r'inserted_at'] = null;
    }
      json[r'name'] = this.name;
    if (this.owner != null) {
      json[r'owner'] = this.owner;
    } else {
      json[r'owner'] = null;
    }
    if (this.ownerId != null) {
      json[r'owner_id'] = this.ownerId;
    } else {
      json[r'owner_id'] = null;
    }
    if (this.ownerUuid != null) {
      json[r'owner_uuid'] = this.ownerUuid;
    } else {
      json[r'owner_uuid'] = null;
    }
    if (this.projectId != null) {
      json[r'project_id'] = this.projectId;
    } else {
      json[r'project_id'] = null;
    }
    if (this.projectUuid != null) {
      json[r'project_uuid'] = this.projectUuid;
    } else {
      json[r'project_uuid'] = null;
    }
    if (this.status != null) {
      json[r'status'] = this.status;
    } else {
      json[r'status'] = null;
    }
      json[r'type'] = this.type;
    if (this.updatedAt != null) {
      json[r'updated_at'] = this.updatedAt;
    } else {
      json[r'updated_at'] = null;
    }
    if (this.updatedBy != null) {
      json[r'updated_by'] = this.updatedBy;
    } else {
      json[r'updated_by'] = null;
    }
      json[r'visibility'] = this.visibility;
    return json;
  }

  /// Returns a new [SnippetBody] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static SnippetBody? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{r'description', r'folder_id', r'inserted_at', r'owner', r'owner_id', r'owner_uuid', r'project_id', r'project_uuid', r'status', r'updated_at', r'updated_by'};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return SnippetBody(
        content: SqlContent.fromJson(json[r'content'])!,
        description: mapValueOfType<String>(json, r'description'),
        favorite: mapValueOfType<bool>(json, r'favorite') ?? false,
        folderId: mapValueOfType<String>(json, r'folder_id'),
        id: mapValueOfType<String>(json, r'id')!,
        insertedAt: mapValueOfType<String>(json, r'inserted_at'),
        name: mapValueOfType<String>(json, r'name')!,
        owner: mapCastOfType<String, Object>(json, r'owner') ?? const {},
        ownerId: OwnerId.fromJson(json[r'owner_id']),
        ownerUuid: mapValueOfType<String>(json, r'owner_uuid'),
        projectId: ProjectId.fromJson(json[r'project_id']),
        projectUuid: mapValueOfType<String>(json, r'project_uuid'),
        status: mapValueOfType<String>(json, r'status'),
        type: mapValueOfType<String>(json, r'type')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at'),
        updatedBy: mapCastOfType<String, Object>(json, r'updated_by') ?? const {},
        visibility: mapValueOfType<String>(json, r'visibility')!,
      );
    }
    return null;
  }

  static List<SnippetBody> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <SnippetBody>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = SnippetBody.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, SnippetBody> mapFromJson(dynamic json) {
    final map = <String, SnippetBody>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = SnippetBody.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of SnippetBody-objects as value to a dart map
  static Map<String, List<SnippetBody>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<SnippetBody>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = SnippetBody.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'content',
    'id',
    'name',
    'type',
    'visibility',
  };
}

