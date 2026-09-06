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
  /// * [String] projectName (required):
  Future<Response> getProjectConfigTokenApiProjectsProjectNameConfigTokenGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/config-token'
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

  /// Get Project Config Token
  ///
  /// Entrega o token compartilhado aos membros do projeto e registra a leitura.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Object?> getProjectConfigTokenApiProjectsProjectNameConfigTokenGet(String projectName,) async {
    final response = await getProjectConfigTokenApiProjectsProjectNameConfigTokenGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'Object',) as Object;
    
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
  /// * [String] projectName (required):
  Future<Response> getProjectQueueStatusApiProjectsProjectNameQueueStatusGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/queue-status'
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

  /// Get Project Queue Status
  ///
  /// Retorna o estado atual da fila de ações do projeto.  Inclui o job em execução (se houver), o tamanho da fila, e os jobs pendentes/rodando do banco para fins de UI (polling).
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Object?> getProjectQueueStatusApiProjectsProjectNameQueueStatusGet(String projectName,) async {
    final response = await getProjectQueueStatusApiProjectsProjectNameQueueStatusGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'Object',) as Object;
    
    }
    return null;
  }

  /// Get Project Rename History
  ///
  /// Retorna auditoria e historico duravel de nome/path do projeto.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [int] limit:
  Future<Response> getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGetWithHttpInfo(String projectName, { int? limit, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/rename-history'
      .replaceAll('{project_name}', projectName);

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
  /// Retorna auditoria e historico duravel de nome/path do projeto.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [int] limit:
  Future<Object?> getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGet(String projectName, { int? limit, }) async {
    final response = await getProjectRenameHistoryApiProjectsProjectNameRenameHistoryGetWithHttpInfo(projectName,  limit: limit, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'Object',) as Object;
    
    }
    return null;
  }

  /// Rename Project
  ///
  /// Renomeia o slug/path do projeto (migração completa em background).  O escopo inclui: nome interno na meta DB, banco Postgres, roles por projeto, replication slots do Realtime, tenant Supavisor, diretório físico e templates (nginx, docker-compose, .env).
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectRenameRequest] projectRenameRequest (required):
  Future<Response> renameProjectApiProjectsProjectNameRenamePostWithHttpInfo(String projectName, ProjectRenameRequest projectRenameRequest,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/rename'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = projectRenameRequest;

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
  /// Renomeia o slug/path do projeto (migração completa em background).  O escopo inclui: nome interno na meta DB, banco Postgres, roles por projeto, replication slots do Realtime, tenant Supavisor, diretório físico e templates (nginx, docker-compose, .env).
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [ProjectRenameRequest] projectRenameRequest (required):
  Future<Object?> renameProjectApiProjectsProjectNameRenamePost(String projectName, ProjectRenameRequest projectRenameRequest,) async {
    final response = await renameProjectApiProjectsProjectNameRenamePostWithHttpInfo(projectName, projectRenameRequest,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'Object',) as Object;
    
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
  /// * [String] projectName (required):
  ///
  /// * [ProjectDisplayNameUpdate] projectDisplayNameUpdate (required):
  Future<Response> updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatchWithHttpInfo(String projectName, ProjectDisplayNameUpdate projectDisplayNameUpdate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/display-name'
      .replaceAll('{project_name}', projectName);

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
  /// * [String] projectName (required):
  ///
  /// * [ProjectDisplayNameUpdate] projectDisplayNameUpdate (required):
  Future<Object?> updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatch(String projectName, ProjectDisplayNameUpdate projectDisplayNameUpdate,) async {
    final response = await updateProjectDisplayNameApiProjectsProjectNameDisplayNamePatchWithHttpInfo(projectName, projectDisplayNameUpdate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'Object',) as Object;
    
    }
    return null;
  }
}
