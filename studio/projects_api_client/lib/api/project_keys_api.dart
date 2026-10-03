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
  /// * [String] projectRef (required):
  Future<Response> rotateProjectKeyApiProjectsProjectRefRotateKeyPostWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/rotate-key'
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

  /// Rotate Project Key
  ///
  /// Rotaciona anon/service_role via script. Enfileirado por projeto.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<RotateProjectKeyResponse?> rotateProjectKeyApiProjectsProjectRefRotateKeyPost(String projectRef,) async {
    final response = await rotateProjectKeyApiProjectsProjectRefRotateKeyPostWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RotateProjectKeyResponse',) as RotateProjectKeyResponse;
    
    }
    return null;
  }

  /// Update Automatic Key Rotation
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [AutomaticKeyRotationUpdate] automaticKeyRotationUpdate (required):
  Future<Response> updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPutWithHttpInfo(String projectRef, AutomaticKeyRotationUpdate automaticKeyRotationUpdate,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/automatic-key-rotation'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [AutomaticKeyRotationUpdate] automaticKeyRotationUpdate (required):
  Future<AutomaticKeyRotationResponse?> updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPut(String projectRef, AutomaticKeyRotationUpdate automaticKeyRotationUpdate,) async {
    final response = await updateAutomaticKeyRotationApiProjectsProjectRefAutomaticKeyRotationPutWithHttpInfo(projectRef, automaticKeyRotationUpdate,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'AutomaticKeyRotationResponse',) as AutomaticKeyRotationResponse;
    
    }
    return null;
  }
}
