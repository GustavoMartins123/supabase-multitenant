//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class InternalApi {
  InternalApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Enc Key
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> encKeyApiProjectsInternalEncKeyRefGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/enc-key/{ref}'
      .replaceAll('{ref}', ref);

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

  /// Enc Key
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<EncKeyResponse?> encKeyApiProjectsInternalEncKeyRefGet(String ref,) async {
    final response = await encKeyApiProjectsInternalEncKeyRefGetWithHttpInfo(ref,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'EncKeyResponse',) as EncKeyResponse;
    
    }
    return null;
  }

  /// Get Content Project Identity
  ///
  /// Resolve o slug mutável para o UUID estável usado apenas por content.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/content-identity/{project_name}'
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

  /// Get Content Project Identity
  ///
  /// Resolve o slug mutável para o UUID estável usado apenas por content.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<ContentIdentityResponse?> getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGet(String projectName,) async {
    final response = await getContentProjectIdentityApiProjectsInternalContentIdentityProjectNameGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ContentIdentityResponse',) as ContentIdentityResponse;
    
    }
    return null;
  }

  /// Get Studio Project Context
  ///
  /// Resolve and authorize the project carried by the Studio URL.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> getStudioProjectContextApiProjectsInternalStudioContextRefGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/studio-context/{ref}'
      .replaceAll('{ref}', ref);

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

  /// Get Studio Project Context
  ///
  /// Resolve and authorize the project carried by the Studio URL.
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<StudioContextResponse?> getStudioProjectContextApiProjectsInternalStudioContextRefGet(String ref,) async {
    final response = await getStudioProjectContextApiProjectsInternalStudioContextRefGetWithHttpInfo(ref,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'StudioContextResponse',) as StudioContextResponse;
    
    }
    return null;
  }

  /// Project Key Version
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> projectKeyVersionApiProjectsInternalKeyVersionRefGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/key-version/{ref}'
      .replaceAll('{ref}', ref);

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

  /// Project Key Version
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<KeyVersionResponse?> projectKeyVersionApiProjectsInternalKeyVersionRefGet(String ref,) async {
    final response = await projectKeyVersionApiProjectsInternalKeyVersionRefGetWithHttpInfo(ref,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'KeyVersionResponse',) as KeyVersionResponse;
    
    }
    return null;
  }

  /// Proxy Global Analytics
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Response> proxyGlobalAnalyticsDeleteWithHttpInfo(String analyticsPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/internal/analytics/{analytics_path}'
      .replaceAll('{analytics_path}', analyticsPath);

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

  /// Proxy Global Analytics
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Object?> proxyGlobalAnalyticsDelete(String analyticsPath,) async {
    final response = await proxyGlobalAnalyticsDeleteWithHttpInfo(analyticsPath,);
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

  /// Proxy Global Analytics
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Response> proxyGlobalAnalyticsGetWithHttpInfo(String analyticsPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/internal/analytics/{analytics_path}'
      .replaceAll('{analytics_path}', analyticsPath);

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

  /// Proxy Global Analytics
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Object?> proxyGlobalAnalyticsGet(String analyticsPath,) async {
    final response = await proxyGlobalAnalyticsGetWithHttpInfo(analyticsPath,);
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

  /// Proxy Global Analytics
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Response> proxyGlobalAnalyticsPostWithHttpInfo(String analyticsPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/internal/analytics/{analytics_path}'
      .replaceAll('{analytics_path}', analyticsPath);

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

  /// Proxy Global Analytics
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Object?> proxyGlobalAnalyticsPost(String analyticsPath,) async {
    final response = await proxyGlobalAnalyticsPostWithHttpInfo(analyticsPath,);
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

  /// Proxy Global Analytics
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Response> proxyGlobalAnalyticsPutWithHttpInfo(String analyticsPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/internal/analytics/{analytics_path}'
      .replaceAll('{analytics_path}', analyticsPath);

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

  /// Proxy Global Analytics
  ///
  /// Parameters:
  ///
  /// * [String] analyticsPath (required):
  Future<Object?> proxyGlobalAnalyticsPut(String analyticsPath,) async {
    final response = await proxyGlobalAnalyticsPutWithHttpInfo(analyticsPath,);
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

  /// Sync User Identity
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [UserSyncPayload] userSyncPayload (required):
  Future<Response> syncUserIdentityApiProjectsInternalUsersSyncPostWithHttpInfo(UserSyncPayload userSyncPayload,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/internal/users/sync';

    // ignore: prefer_final_locals
    Object? postBody = userSyncPayload;

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

  /// Sync User Identity
  ///
  /// Parameters:
  ///
  /// * [UserSyncPayload] userSyncPayload (required):
  Future<UserSyncResponse?> syncUserIdentityApiProjectsInternalUsersSyncPost(UserSyncPayload userSyncPayload,) async {
    final response = await syncUserIdentityApiProjectsInternalUsersSyncPostWithHttpInfo(userSyncPayload,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'UserSyncResponse',) as UserSyncResponse;
    
    }
    return null;
  }
}
