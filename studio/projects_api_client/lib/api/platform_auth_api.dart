//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class PlatformAuthApi {
  PlatformAuthApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// List Project Auth Users
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [int] page:
  ///
  /// * [int] perPage:
  Future<Response> listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGetWithHttpInfo(String projectName, { int? page, int? perPage, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/auth-users/{project_name}'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (page != null) {
      queryParams.addAll(_queryParams('', 'page', page));
    }
    if (perPage != null) {
      queryParams.addAll(_queryParams('', 'per_page', perPage));
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

  /// List Project Auth Users
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [int] page:
  ///
  /// * [int] perPage:
  Future<AuthUsersResponse?> listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGet(String projectName, { int? page, int? perPage, }) async {
    final response = await listProjectAuthUsersApiProjectsInternalAuthUsersProjectNameGetWithHttpInfo(projectName,  page: page, perPage: perPage, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'AuthUsersResponse',) as AuthUsersResponse;
    
    }
    return null;
  }

  /// Proxy Project Auth Admin
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Response> proxyProjectAuthAdminDeleteWithHttpInfo(String projectName, String gotruePath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/auth-admin/{project_name}/{gotrue_path}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{gotrue_path}', gotruePath);

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

  /// Proxy Project Auth Admin
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Object?> proxyProjectAuthAdminDelete(String projectName, String gotruePath,) async {
    final response = await proxyProjectAuthAdminDeleteWithHttpInfo(projectName, gotruePath,);
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

  /// Proxy Project Auth Admin
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Response> proxyProjectAuthAdminGetWithHttpInfo(String projectName, String gotruePath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/auth-admin/{project_name}/{gotrue_path}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{gotrue_path}', gotruePath);

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

  /// Proxy Project Auth Admin
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Object?> proxyProjectAuthAdminGet(String projectName, String gotruePath,) async {
    final response = await proxyProjectAuthAdminGetWithHttpInfo(projectName, gotruePath,);
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

  /// Proxy Project Auth Admin
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Response> proxyProjectAuthAdminPatchWithHttpInfo(String projectName, String gotruePath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/auth-admin/{project_name}/{gotrue_path}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{gotrue_path}', gotruePath);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>[];


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

  /// Proxy Project Auth Admin
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Object?> proxyProjectAuthAdminPatch(String projectName, String gotruePath,) async {
    final response = await proxyProjectAuthAdminPatchWithHttpInfo(projectName, gotruePath,);
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

  /// Proxy Project Auth Admin
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Response> proxyProjectAuthAdminPostWithHttpInfo(String projectName, String gotruePath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/auth-admin/{project_name}/{gotrue_path}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{gotrue_path}', gotruePath);

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

  /// Proxy Project Auth Admin
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Object?> proxyProjectAuthAdminPost(String projectName, String gotruePath,) async {
    final response = await proxyProjectAuthAdminPostWithHttpInfo(projectName, gotruePath,);
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

  /// Proxy Project Auth Admin
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Response> proxyProjectAuthAdminPutWithHttpInfo(String projectName, String gotruePath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/auth-admin/{project_name}/{gotrue_path}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{gotrue_path}', gotruePath);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>[];


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

  /// Proxy Project Auth Admin
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] gotruePath (required):
  Future<Object?> proxyProjectAuthAdminPut(String projectName, String gotruePath,) async {
    final response = await proxyProjectAuthAdminPutWithHttpInfo(projectName, gotruePath,);
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
