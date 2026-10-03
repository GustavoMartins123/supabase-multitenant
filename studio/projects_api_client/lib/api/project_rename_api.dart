//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class ProjectRenameApi {
  ProjectRenameApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Get Project Config Token
  ///
  /// Entrega o token compartilhado aos membros do projeto e registra a leitura.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> getProjectConfigTokenApiProjectsProjectRefConfigTokenGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/config-token'
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

  /// Get Project Config Token
  ///
  /// Entrega o token compartilhado aos membros do projeto e registra a leitura.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<ProjectConfigTokenResponse?> getProjectConfigTokenApiProjectsProjectRefConfigTokenGet(String projectRef,) async {
    final response = await getProjectConfigTokenApiProjectsProjectRefConfigTokenGetWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ProjectConfigTokenResponse',) as ProjectConfigTokenResponse;
    
    }
    return null;
  }

  /// Get Project Queue Status
  ///
  /// Retorna o estado atual da fila de ações do projeto.  Inclui o job em execução (se houver), o tamanho da fila, e os jobs pendentes/rodando do banco para fins de UI (polling).
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> getProjectQueueStatusApiProjectsProjectRefQueueStatusGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/queue-status'
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

  /// Get Project Queue Status
  ///
  /// Retorna o estado atual da fila de ações do projeto.  Inclui o job em execução (se houver), o tamanho da fila, e os jobs pendentes/rodando do banco para fins de UI (polling).
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<ProjectQueueStatusResponse?> getProjectQueueStatusApiProjectsProjectRefQueueStatusGet(String projectRef,) async {
    final response = await getProjectQueueStatusApiProjectsProjectRefQueueStatusGetWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ProjectQueueStatusResponse',) as ProjectQueueStatusResponse;
    
    }
    return null;
  }

  /// Get Project Rename History
  ///
  /// Retorna auditoria e historico duravel da referencia publica.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [int] limit:
  Future<Response> getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGetWithHttpInfo(String projectRef, { int? limit, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/rename-history'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (limit != null) {
      queryParams.addAll(_queryParams('', 'limit', limit));
    }

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

  /// Get Project Rename History
  ///
  /// Retorna auditoria e historico duravel da referencia publica.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [int] limit:
  Future<ProjectRenameHistoryResponse?> getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGet(String projectRef, { int? limit, }) async {
    final response = await getProjectRenameHistoryApiProjectsProjectRefRenameHistoryGetWithHttpInfo(projectRef,  limit: limit, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ProjectRenameHistoryResponse',) as ProjectRenameHistoryResponse;
    
    }
    return null;
  }

  /// Rename Project
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [Object] body (required):
  Future<Response> renameProjectApiProjectsProjectRefRenamePostWithHttpInfo(String projectRef, Object body,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/rename'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody = body;

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

  /// Rename Project
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [Object] body (required):
  Future<RenameProjectResponse?> renameProjectApiProjectsProjectRefRenamePost(String projectRef, Object body,) async {
    final response = await renameProjectApiProjectsProjectRefRenamePostWithHttpInfo(projectRef, body,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RenameProjectResponse',) as RenameProjectResponse;
    
    }
    return null;
  }

  /// Update Project Display Name
  ///
  /// Atualiza apenas o display_name do projeto (sem migrar infraestrutura).
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [ProjectDisplayNameUpdate] projectDisplayNameUpdate (required):
  Future<Response> updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatchWithHttpInfo(String projectRef, ProjectDisplayNameUpdate projectDisplayNameUpdate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/display-name'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody = projectDisplayNameUpdate;

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

  /// Update Project Display Name
  ///
  /// Atualiza apenas o display_name do projeto (sem migrar infraestrutura).
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [ProjectDisplayNameUpdate] projectDisplayNameUpdate (required):
  Future<UpdateDisplayNameResponse?> updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatch(String projectRef, ProjectDisplayNameUpdate projectDisplayNameUpdate,) async {
    final response = await updateProjectDisplayNameApiProjectsProjectRefDisplayNamePatchWithHttpInfo(projectRef, projectDisplayNameUpdate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'UpdateDisplayNameResponse',) as UpdateDisplayNameResponse;
    
    }
    return null;
  }
}
