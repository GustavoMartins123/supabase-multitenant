//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class CollaborationApi {
  CollaborationApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Assign Project Tag
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectTagAssign] projectTagAssign (required):
  Future<Response> assignProjectTagApiProjectsProjectNameTagsPostWithHttpInfo(String projectName, ProjectTagAssign projectTagAssign,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/tags'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = projectTagAssign;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


    return apiClient.invokeAPI(
      path,
      'POST',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Assign Project Tag
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectTagAssign] projectTagAssign (required):
  Future<AssignProjectTagResponse?> assignProjectTagApiProjectsProjectNameTagsPost(String projectName, ProjectTagAssign projectTagAssign,) async {
    final response = await assignProjectTagApiProjectsProjectNameTagsPostWithHttpInfo(projectName, projectTagAssign,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'AssignProjectTagResponse',) as AssignProjectTagResponse;
    
    }
    return null;
  }

  /// Create Project Hint
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectHintCreate] projectHintCreate (required):
  Future<Response> createProjectHintApiProjectsProjectNameHintsPostWithHttpInfo(String projectName, ProjectHintCreate projectHintCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/hints'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = projectHintCreate;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


    return apiClient.invokeAPI(
      path,
      'POST',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Create Project Hint
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectHintCreate] projectHintCreate (required):
  Future<CreateProjectHintResponse?> createProjectHintApiProjectsProjectNameHintsPost(String projectName, ProjectHintCreate projectHintCreate,) async {
    final response = await createProjectHintApiProjectsProjectNameHintsPostWithHttpInfo(projectName, projectHintCreate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'CreateProjectHintResponse',) as CreateProjectHintResponse;
    
    }
    return null;
  }

  /// Create Project Note
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectNoteCreate] projectNoteCreate (required):
  Future<Response> createProjectNoteApiProjectsProjectNameNotesPostWithHttpInfo(String projectName, ProjectNoteCreate projectNoteCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/notes'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = projectNoteCreate;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


    return apiClient.invokeAPI(
      path,
      'POST',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Create Project Note
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectNoteCreate] projectNoteCreate (required):
  Future<CreateProjectNoteResponse?> createProjectNoteApiProjectsProjectNameNotesPost(String projectName, ProjectNoteCreate projectNoteCreate,) async {
    final response = await createProjectNoteApiProjectsProjectNameNotesPostWithHttpInfo(projectName, projectNoteCreate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'CreateProjectNoteResponse',) as CreateProjectNoteResponse;
    
    }
    return null;
  }

  /// Create Project Thread Message
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectThreadMessageCreate] projectThreadMessageCreate (required):
  Future<Response> createProjectThreadMessageApiProjectsProjectNameThreadMessagesPostWithHttpInfo(String projectName, ProjectThreadMessageCreate projectThreadMessageCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/thread/messages'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = projectThreadMessageCreate;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


    return apiClient.invokeAPI(
      path,
      'POST',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Create Project Thread Message
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectThreadMessageCreate] projectThreadMessageCreate (required):
  Future<CreateThreadMessageResponse?> createProjectThreadMessageApiProjectsProjectNameThreadMessagesPost(String projectName, ProjectThreadMessageCreate projectThreadMessageCreate,) async {
    final response = await createProjectThreadMessageApiProjectsProjectNameThreadMessagesPostWithHttpInfo(projectName, projectThreadMessageCreate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'CreateThreadMessageResponse',) as CreateThreadMessageResponse;
    
    }
    return null;
  }

  /// Delete Project Note
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] noteId (required):
  Future<Response> deleteProjectNoteApiProjectsProjectNameNotesNoteIdDeleteWithHttpInfo(String projectName, String noteId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/notes/{note_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{note_id}', noteId);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>[];


    return apiClient.invokeAPI(
      path,
      'DELETE',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Delete Project Note
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] noteId (required):
  Future<DeleteProjectNoteResponse?> deleteProjectNoteApiProjectsProjectNameNotesNoteIdDelete(String projectName, String noteId,) async {
    final response = await deleteProjectNoteApiProjectsProjectNameNotesNoteIdDeleteWithHttpInfo(projectName, noteId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'DeleteProjectNoteResponse',) as DeleteProjectNoteResponse;
    
    }
    return null;
  }

  /// Get Project Collaboration
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> getProjectCollaborationApiProjectsProjectNameCollaborationGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/collaboration'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>[];


    return apiClient.invokeAPI(
      path,
      'GET',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Get Project Collaboration
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<GetProjectCollaborationResponse?> getProjectCollaborationApiProjectsProjectNameCollaborationGet(String projectName,) async {
    final response = await getProjectCollaborationApiProjectsProjectNameCollaborationGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'GetProjectCollaborationResponse',) as GetProjectCollaborationResponse;
    
    }
    return null;
  }

  /// Unassign Project Tag
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] tagId (required):
  Future<Response> unassignProjectTagApiProjectsProjectNameTagsTagIdDeleteWithHttpInfo(String projectName, String tagId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/tags/{tag_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{tag_id}', tagId);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>[];


    return apiClient.invokeAPI(
      path,
      'DELETE',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Unassign Project Tag
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] tagId (required):
  Future<UnassignProjectTagResponse?> unassignProjectTagApiProjectsProjectNameTagsTagIdDelete(String projectName, String tagId,) async {
    final response = await unassignProjectTagApiProjectsProjectNameTagsTagIdDeleteWithHttpInfo(projectName, tagId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'UnassignProjectTagResponse',) as UnassignProjectTagResponse;
    
    }
    return null;
  }

  /// Update Project Hint Status
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] hintId (required):
  ///
  /// * [ProjectHintStatusUpdate] projectHintStatusUpdate (required):
  Future<Response> updateProjectHintStatusApiProjectsProjectNameHintsHintIdPutWithHttpInfo(String projectName, String hintId, ProjectHintStatusUpdate projectHintStatusUpdate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/hints/{hint_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{hint_id}', hintId);

    // ignore: prefer_final_locals
    Object? postBody = projectHintStatusUpdate;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


    return apiClient.invokeAPI(
      path,
      'PUT',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Update Project Hint Status
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] hintId (required):
  ///
  /// * [ProjectHintStatusUpdate] projectHintStatusUpdate (required):
  Future<UpdateProjectHintResponse?> updateProjectHintStatusApiProjectsProjectNameHintsHintIdPut(String projectName, String hintId, ProjectHintStatusUpdate projectHintStatusUpdate,) async {
    final response = await updateProjectHintStatusApiProjectsProjectNameHintsHintIdPutWithHttpInfo(projectName, hintId, projectHintStatusUpdate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'UpdateProjectHintResponse',) as UpdateProjectHintResponse;
    
    }
    return null;
  }

  /// Update Project Notification Read State
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] notificationId (required):
  ///
  /// * [ProjectNotificationRead] projectNotificationRead (required):
  Future<Response> updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatchWithHttpInfo(String projectName, String notificationId, ProjectNotificationRead projectNotificationRead,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/notifications/{notification_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{notification_id}', notificationId);

    // ignore: prefer_final_locals
    Object? postBody = projectNotificationRead;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


    return apiClient.invokeAPI(
      path,
      'PATCH',
      queryParams,
      postBody,
      headerParams,
      formParams,
      contentTypes.isEmpty ? null : contentTypes.first,
    );
  }

  /// Update Project Notification Read State
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] notificationId (required):
  ///
  /// * [ProjectNotificationRead] projectNotificationRead (required):
  Future<UpdateNotificationReadResponse?> updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatch(String projectName, String notificationId, ProjectNotificationRead projectNotificationRead,) async {
    final response = await updateProjectNotificationReadStateApiProjectsProjectNameNotificationsNotificationIdPatchWithHttpInfo(projectName, notificationId, projectNotificationRead,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'UpdateNotificationReadResponse',) as UpdateNotificationReadResponse;
    
    }
    return null;
  }
}
