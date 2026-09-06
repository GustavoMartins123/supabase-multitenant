//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class GetProjectCollaborationResponse {
  /// Returns a new [GetProjectCollaborationResponse] instance.
  GetProjectCollaborationResponse({
    this.assignedTags = const [],
    this.availableTags = const [],
    this.hints = const [],
    this.members = const [],
    this.notes = const [],
    this.notifications = const [],
    required this.project,
    this.threadMessages = const [],
  });

  List<CollaborationTagItem> assignedTags;

  List<CollaborationTagItem> availableTags;

  List<CollaborationHintItem> hints;

  List<CollaborationMemberItem> members;

  List<CollaborationNoteItem> notes;

  List<CollaborationNotificationItem> notifications;

  String project;

  List<CollaborationThreadItem> threadMessages;

  @override
  bool operator ==(Object other) => identical(this, other) || other is GetProjectCollaborationResponse &&
    _deepEquality.equals(other.assignedTags, assignedTags) &&
    _deepEquality.equals(other.availableTags, availableTags) &&
    _deepEquality.equals(other.hints, hints) &&
    _deepEquality.equals(other.members, members) &&
    _deepEquality.equals(other.notes, notes) &&
    _deepEquality.equals(other.notifications, notifications) &&
    other.project == project &&
    _deepEquality.equals(other.threadMessages, threadMessages);

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (assignedTags.hashCode) +
    (availableTags.hashCode) +
    (hints.hashCode) +
    (members.hashCode) +
    (notes.hashCode) +
    (notifications.hashCode) +
    (project.hashCode) +
    (threadMessages.hashCode);

  @override
  String toString() => 'GetProjectCollaborationResponse[assignedTags=$assignedTags, availableTags=$availableTags, hints=$hints, members=$members, notes=$notes, notifications=$notifications, project=$project, threadMessages=$threadMessages]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'assigned_tags'] = this.assignedTags;
      json[r'available_tags'] = this.availableTags;
      json[r'hints'] = this.hints;
      json[r'members'] = this.members;
      json[r'notes'] = this.notes;
      json[r'notifications'] = this.notifications;
      json[r'project'] = this.project;
      json[r'thread_messages'] = this.threadMessages;
    return json;
  }

  /// Returns a new [GetProjectCollaborationResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static GetProjectCollaborationResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "GetProjectCollaborationResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "GetProjectCollaborationResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return GetProjectCollaborationResponse(
        assignedTags: CollaborationTagItem.listFromJson(json[r'assigned_tags']),
        availableTags: CollaborationTagItem.listFromJson(json[r'available_tags']),
        hints: CollaborationHintItem.listFromJson(json[r'hints']),
        members: CollaborationMemberItem.listFromJson(json[r'members']),
        notes: CollaborationNoteItem.listFromJson(json[r'notes']),
        notifications: CollaborationNotificationItem.listFromJson(json[r'notifications']),
        project: mapValueOfType<String>(json, r'project')!,
        threadMessages: CollaborationThreadItem.listFromJson(json[r'thread_messages']),
      );
    }
    return null;
  }

  static List<GetProjectCollaborationResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <GetProjectCollaborationResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = GetProjectCollaborationResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, GetProjectCollaborationResponse> mapFromJson(dynamic json) {
    final map = <String, GetProjectCollaborationResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = GetProjectCollaborationResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of GetProjectCollaborationResponse-objects as value to a dart map
  static Map<String, List<GetProjectCollaborationResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<GetProjectCollaborationResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = GetProjectCollaborationResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'assigned_tags',
    'available_tags',
    'hints',
    'members',
    'notes',
    'notifications',
    'project',
    'thread_messages',
  };
}

