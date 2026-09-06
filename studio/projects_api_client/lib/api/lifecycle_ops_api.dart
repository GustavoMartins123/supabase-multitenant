//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class LifecycleOpsApi {
  LifecycleOpsApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Get Project Settings
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> getProjectSettingsApiProjectsProjectNameSettingsGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/settings'
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

  /// Get Project Settings
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<GetProjectSettingsResponse?> getProjectSettingsApiProjectsProjectNameSettingsGet(String projectName,) async {
    final response = await getProjectSettingsApiProjectsProjectNameSettingsGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'GetProjectSettingsResponse',) as GetProjectSettingsResponse;
    
    }
    return null;
  }

  /// Recreate Project Services
  ///
  /// Recreate specific services of a project using docker compose down + up. This is needed (instead of just restart) because env vars are read at container creation time, not on restart.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [RecreateServices] recreateServices (required):
  Future<Response> recreateProjectServicesApiProjectsProjectNameRecreateServicesPostWithHttpInfo(String projectName, RecreateServices recreateServices,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/recreate-services'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = recreateServices;

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

  /// Recreate Project Services
  ///
  /// Recreate specific services of a project using docker compose down + up. This is needed (instead of just restart) because env vars are read at container creation time, not on restart.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [RecreateServices] recreateServices (required):
  Future<RecreateProjectServicesResponse?> recreateProjectServicesApiProjectsProjectNameRecreateServicesPost(String projectName, RecreateServices recreateServices,) async {
    final response = await recreateProjectServicesApiProjectsProjectNameRecreateServicesPostWithHttpInfo(projectName, recreateServices,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RecreateProjectServicesResponse',) as RecreateProjectServicesResponse;
    
    }
    return null;
  }

  /// Restart Project
  ///
  /// Reinicia os containers do projeto. Enfileirado por projeto.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> restartProjectApiProjectsProjectNameRestartPostWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/restart'
      .replaceAll('{project_name}', projectName);

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

  /// Restart Project
  ///
  /// Reinicia os containers do projeto. Enfileirado por projeto.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<RestartProjectResponse?> restartProjectApiProjectsProjectNameRestartPost(String projectName,) async {
    final response = await restartProjectApiProjectsProjectNameRestartPostWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RestartProjectResponse',) as RestartProjectResponse;
    
    }
    return null;
  }

  /// Start Project
  ///
  /// Inicia os containers do projeto. Enfileirado por projeto.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> startProjectApiProjectsProjectNameStartPostWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/start'
      .replaceAll('{project_name}', projectName);

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

  /// Start Project
  ///
  /// Inicia os containers do projeto. Enfileirado por projeto.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<StartProjectResponse?> startProjectApiProjectsProjectNameStartPost(String projectName,) async {
    final response = await startProjectApiProjectsProjectNameStartPostWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'StartProjectResponse',) as StartProjectResponse;
    
    }
    return null;
  }

  /// Stop Project
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> stopProjectApiProjectsProjectNameStopPostWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/stop'
      .replaceAll('{project_name}', projectName);

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

  /// Stop Project
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<StopProjectResponse?> stopProjectApiProjectsProjectNameStopPost(String projectName,) async {
    final response = await stopProjectApiProjectsProjectNameStopPostWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'StopProjectResponse',) as StopProjectResponse;
    
    }
    return null;
  }

  /// Update Project Settings
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [UpdateSettings] updateSettings (required):
  Future<Response> updateProjectSettingsApiProjectsProjectNameSettingsPutWithHttpInfo(String projectName, UpdateSettings updateSettings,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/settings'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = updateSettings;

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

  /// Update Project Settings
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [UpdateSettings] updateSettings (required):
  Future<UpdateProjectSettingsResponse?> updateProjectSettingsApiProjectsProjectNameSettingsPut(String projectName, UpdateSettings updateSettings,) async {
    final response = await updateProjectSettingsApiProjectsProjectNameSettingsPutWithHttpInfo(projectName, updateSettings,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'UpdateProjectSettingsResponse',) as UpdateProjectSettingsResponse;
    
    }
    return null;
  }
}
