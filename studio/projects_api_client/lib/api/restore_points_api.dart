//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class RestorePointsApi {
  RestorePointsApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Create Project Restore Point
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [RestorePointCreate] restorePointCreate (required):
  Future<Response> createProjectRestorePointApiProjectsProjectNameRestorePointsPostWithHttpInfo(String projectName, RestorePointCreate restorePointCreate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/restore-points'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = restorePointCreate;

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

  /// Create Project Restore Point
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [RestorePointCreate] restorePointCreate (required):
  Future<CreateRestorePointResponse?> createProjectRestorePointApiProjectsProjectNameRestorePointsPost(String projectName, RestorePointCreate restorePointCreate,) async {
    final response = await createProjectRestorePointApiProjectsProjectNameRestorePointsPostWithHttpInfo(projectName, restorePointCreate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'CreateRestorePointResponse',) as CreateRestorePointResponse;
    
    }
    return null;
  }

  /// Delete Project Restore Point
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] pointId (required):
  Future<Response> deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDeleteWithHttpInfo(String projectName, String pointId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/restore-points/{point_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{point_id}', pointId);

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

  /// Delete Project Restore Point
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] pointId (required):
  Future<DeleteRestorePointResponse?> deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDelete(String projectName, String pointId,) async {
    final response = await deleteProjectRestorePointApiProjectsProjectNameRestorePointsPointIdDeleteWithHttpInfo(projectName, pointId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'DeleteRestorePointResponse',) as DeleteRestorePointResponse;
    
    }
    return null;
  }

  /// List Project Restore Points
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> listProjectRestorePointsApiProjectsProjectNameRestorePointsGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/restore-points'
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

  /// List Project Restore Points
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<ListRestorePointsResponse?> listProjectRestorePointsApiProjectsProjectNameRestorePointsGet(String projectName,) async {
    final response = await listProjectRestorePointsApiProjectsProjectNameRestorePointsGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ListRestorePointsResponse',) as ListRestorePointsResponse;
    
    }
    return null;
  }

  /// Restore Project Restore Point
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] pointId (required):
  Future<Response> restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePostWithHttpInfo(String projectName, String pointId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/restore-points/{point_id}/restore'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{point_id}', pointId);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>[];


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

  /// Restore Project Restore Point
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] pointId (required):
  Future<RestoreRestorePointResponse?> restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePost(String projectName, String pointId,) async {
    final response = await restoreProjectRestorePointApiProjectsProjectNameRestorePointsPointIdRestorePostWithHttpInfo(projectName, pointId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RestoreRestorePointResponse',) as RestoreRestorePointResponse;
    
    }
    return null;
  }
}
