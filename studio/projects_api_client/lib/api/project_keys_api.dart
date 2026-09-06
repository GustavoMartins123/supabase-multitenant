//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class ProjectKeysApi {
  ProjectKeysApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Rotate Project Key
  ///
  /// Rotaciona anon/service_role via script. Enfileirado por projeto.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> rotateProjectKeyApiProjectsProjectNameRotateKeyPostWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/rotate-key'
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

  /// Rotate Project Key
  ///
  /// Rotaciona anon/service_role via script. Enfileirado por projeto.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Object?> rotateProjectKeyApiProjectsProjectNameRotateKeyPost(String projectName,) async {
    final response = await rotateProjectKeyApiProjectsProjectNameRotateKeyPostWithHttpInfo(projectName,);
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

  /// Update Automatic Key Rotation
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [AutomaticKeyRotationUpdate] automaticKeyRotationUpdate (required):
  Future<Response> updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPutWithHttpInfo(String projectName, AutomaticKeyRotationUpdate automaticKeyRotationUpdate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/automatic-key-rotation'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = automaticKeyRotationUpdate;

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

  /// Update Automatic Key Rotation
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [AutomaticKeyRotationUpdate] automaticKeyRotationUpdate (required):
  Future<Object?> updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPut(String projectName, AutomaticKeyRotationUpdate automaticKeyRotationUpdate,) async {
    final response = await updateAutomaticKeyRotationApiProjectsProjectNameAutomaticKeyRotationPutWithHttpInfo(projectName, automaticKeyRotationUpdate,);
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
