//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class ProjectsApi {
  ProjectsApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Create Project
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [NewProject] newProject (required):
  Future<Response> createProjectApiProjectsPostWithHttpInfo(NewProject newProject,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects';

    // ignore: prefer_final_locals
    Object? postBody = newProject;

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

  /// Create Project
  ///
  /// Parameters:
  ///
  /// * [NewProject] newProject (required):
  Future<Object?> createProjectApiProjectsPost(NewProject newProject,) async {
    final response = await createProjectApiProjectsPostWithHttpInfo(newProject,);
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

  /// Delete Project
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> deleteProjectApiProjectsProjectNameDeleteWithHttpInfo(String projectName, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'X-Step-Up-Token'] = parameterToString(xStepUpToken);
    }

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

  /// Delete Project
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] xStepUpToken:
  Future<Object?> deleteProjectApiProjectsProjectNameDelete(String projectName, { String? xStepUpToken, }) async {
    final response = await deleteProjectApiProjectsProjectNameDeleteWithHttpInfo(projectName,  xStepUpToken: xStepUpToken, );
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

  /// Duplicate Project
  ///
  /// Duplica um projeto existente. - Valida acesso do usuário ao projeto original - Cria registro no banco - Dispara job em background para executar script de duplicação
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [DuplicateProject] duplicateProject (required):
  Future<Response> duplicateProjectApiProjectsDuplicatePostWithHttpInfo(DuplicateProject duplicateProject,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/duplicate';

    // ignore: prefer_final_locals
    Object? postBody = duplicateProject;

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

  /// Duplicate Project
  ///
  /// Duplica um projeto existente. - Valida acesso do usuário ao projeto original - Cria registro no banco - Dispara job em background para executar script de duplicação
  ///
  /// Parameters:
  ///
  /// * [DuplicateProject] duplicateProject (required):
  Future<Object?> duplicateProjectApiProjectsDuplicatePost(DuplicateProject duplicateProject,) async {
    final response = await duplicateProjectApiProjectsDuplicatePostWithHttpInfo(duplicateProject,);
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

  /// List Projects
  ///
  /// Note: This method returns the HTTP [Response].
  Future<Response> listProjectsApiProjectsGetWithHttpInfo() async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects';

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

  /// List Projects
  Future<Object?> listProjectsApiProjectsGet() async {
    final response = await listProjectsApiProjectsGetWithHttpInfo();
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
