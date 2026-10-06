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
  /// * [String] projectRef (required):
  Future<Response> getProjectSettingsApiProjectsProjectRefSettingsGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/settings'
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

  /// Get Project Settings
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<GetProjectSettingsResponse?> getProjectSettingsApiProjectsProjectRefSettingsGet(String projectRef,) async {
    final response = await getProjectSettingsApiProjectsProjectRefSettingsGetWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  ///
  /// * [RecreateServices] recreateServices (required):
  Future<Response> recreateProjectServicesApiProjectsProjectRefRecreateServicesPostWithHttpInfo(String projectRef, RecreateServices recreateServices,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/recreate-services'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [RecreateServices] recreateServices (required):
  Future<RecreateProjectServicesResponse?> recreateProjectServicesApiProjectsProjectRefRecreateServicesPost(String projectRef, RecreateServices recreateServices,) async {
    final response = await recreateProjectServicesApiProjectsProjectRefRecreateServicesPostWithHttpInfo(projectRef, recreateServices,);
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
  /// * [String] projectRef (required):
  Future<Response> restartProjectApiProjectsProjectRefRestartPostWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/restart'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  Future<RestartProjectResponse?> restartProjectApiProjectsProjectRefRestartPost(String projectRef,) async {
    final response = await restartProjectApiProjectsProjectRefRestartPostWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  Future<Response> startProjectApiProjectsProjectRefStartPostWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/start'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  Future<StartProjectResponse?> startProjectApiProjectsProjectRefStartPost(String projectRef,) async {
    final response = await startProjectApiProjectsProjectRefStartPostWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  Future<Response> stopProjectApiProjectsProjectRefStopPostWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/stop'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  Future<StopProjectResponse?> stopProjectApiProjectsProjectRefStopPost(String projectRef,) async {
    final response = await stopProjectApiProjectsProjectRefStopPostWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  ///
  /// * [UpdateSettings] updateSettings (required):
  Future<Response> updateProjectSettingsApiProjectsProjectRefSettingsPutWithHttpInfo(String projectRef, UpdateSettings updateSettings,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/settings'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [UpdateSettings] updateSettings (required):
  Future<UpdateProjectSettingsResponse?> updateProjectSettingsApiProjectsProjectRefSettingsPut(String projectRef, UpdateSettings updateSettings,) async {
    final response = await updateProjectSettingsApiProjectsProjectRefSettingsPutWithHttpInfo(projectRef, updateSettings,);
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
