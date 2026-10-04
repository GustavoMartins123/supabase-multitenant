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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectTagAssign] projectTagAssign (required):
  Future<Response> assignProjectTagApiProjectsProjectRefTagsPostWithHttpInfo(String projectRef, ProjectTagAssign projectTagAssign,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/tags'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectTagAssign] projectTagAssign (required):
  Future<AssignProjectTagResponse?> assignProjectTagApiProjectsProjectRefTagsPost(String projectRef, ProjectTagAssign projectTagAssign,) async {
    final response = await assignProjectTagApiProjectsProjectRefTagsPostWithHttpInfo(projectRef, projectTagAssign,);
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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectHintCreate] projectHintCreate (required):
  Future<Response> createProjectHintApiProjectsProjectRefHintsPostWithHttpInfo(String projectRef, ProjectHintCreate projectHintCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/hints'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectHintCreate] projectHintCreate (required):
  Future<CreateProjectHintResponse?> createProjectHintApiProjectsProjectRefHintsPost(String projectRef, ProjectHintCreate projectHintCreate,) async {
    final response = await createProjectHintApiProjectsProjectRefHintsPostWithHttpInfo(projectRef, projectHintCreate,);
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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectNoteCreate] projectNoteCreate (required):
  Future<Response> createProjectNoteApiProjectsProjectRefNotesPostWithHttpInfo(String projectRef, ProjectNoteCreate projectNoteCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/notes'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectNoteCreate] projectNoteCreate (required):
  Future<CreateProjectNoteResponse?> createProjectNoteApiProjectsProjectRefNotesPost(String projectRef, ProjectNoteCreate projectNoteCreate,) async {
    final response = await createProjectNoteApiProjectsProjectRefNotesPostWithHttpInfo(projectRef, projectNoteCreate,);
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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectThreadMessageCreate] projectThreadMessageCreate (required):
  Future<Response> createProjectThreadMessageApiProjectsProjectRefThreadMessagesPostWithHttpInfo(String projectRef, ProjectThreadMessageCreate projectThreadMessageCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/thread/messages'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [ProjectThreadMessageCreate] projectThreadMessageCreate (required):
  Future<CreateThreadMessageResponse?> createProjectThreadMessageApiProjectsProjectRefThreadMessagesPost(String projectRef, ProjectThreadMessageCreate projectThreadMessageCreate,) async {
    final response = await createProjectThreadMessageApiProjectsProjectRefThreadMessagesPostWithHttpInfo(projectRef, projectThreadMessageCreate,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] noteId (required):
  Future<Response> deleteProjectNoteApiProjectsProjectRefNotesNoteIdDeleteWithHttpInfo(String projectRef, String noteId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/notes/{note_id}'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] noteId (required):
  Future<DeleteProjectNoteResponse?> deleteProjectNoteApiProjectsProjectRefNotesNoteIdDelete(String projectRef, String noteId,) async {
    final response = await deleteProjectNoteApiProjectsProjectRefNotesNoteIdDeleteWithHttpInfo(projectRef, noteId,);
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
  /// * [String] projectRef (required):
  Future<Response> getProjectCollaborationApiProjectsProjectRefCollaborationGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/collaboration'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  Future<GetProjectCollaborationResponse?> getProjectCollaborationApiProjectsProjectRefCollaborationGet(String projectRef,) async {
    final response = await getProjectCollaborationApiProjectsProjectRefCollaborationGetWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] tagId (required):
  Future<Response> unassignProjectTagApiProjectsProjectRefTagsTagIdDeleteWithHttpInfo(String projectRef, String tagId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/tags/{tag_id}'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] tagId (required):
  Future<UnassignProjectTagResponse?> unassignProjectTagApiProjectsProjectRefTagsTagIdDelete(String projectRef, String tagId,) async {
    final response = await unassignProjectTagApiProjectsProjectRefTagsTagIdDeleteWithHttpInfo(projectRef, tagId,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] hintId (required):
  ///
  /// * [ProjectHintStatusUpdate] projectHintStatusUpdate (required):
  Future<Response> updateProjectHintStatusApiProjectsProjectRefHintsHintIdPutWithHttpInfo(String projectRef, String hintId, ProjectHintStatusUpdate projectHintStatusUpdate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/hints/{hint_id}'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] hintId (required):
  ///
  /// * [ProjectHintStatusUpdate] projectHintStatusUpdate (required):
  Future<UpdateProjectHintResponse?> updateProjectHintStatusApiProjectsProjectRefHintsHintIdPut(String projectRef, String hintId, ProjectHintStatusUpdate projectHintStatusUpdate,) async {
    final response = await updateProjectHintStatusApiProjectsProjectRefHintsHintIdPutWithHttpInfo(projectRef, hintId, projectHintStatusUpdate,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] notificationId (required):
  ///
  /// * [ProjectNotificationRead] projectNotificationRead (required):
  Future<Response> updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatchWithHttpInfo(String projectRef, String notificationId, ProjectNotificationRead projectNotificationRead,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/notifications/{notification_id}'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] notificationId (required):
  ///
  /// * [ProjectNotificationRead] projectNotificationRead (required):
  Future<UpdateNotificationReadResponse?> updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatch(String projectRef, String notificationId, ProjectNotificationRead projectNotificationRead,) async {
    final response = await updateProjectNotificationReadStateApiProjectsProjectRefNotificationsNotificationIdPatchWithHttpInfo(projectRef, notificationId, projectNotificationRead,);
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
