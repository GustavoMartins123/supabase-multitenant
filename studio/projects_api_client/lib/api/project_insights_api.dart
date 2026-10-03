//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class ProjectInsightsApi {
  ProjectInsightsApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Execute Project Function
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [Map<String, Object>] requestBody (required):
  Future<Response> executeProjectFunctionApiProjectsRefExecuteFunctionPostWithHttpInfo(String ref, Map<String, Object> requestBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/execute-function'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = requestBody;

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

  /// Execute Project Function
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [Map<String, Object>] requestBody (required):
  Future<List<Map<String, Object>>?> executeProjectFunctionApiProjectsRefExecuteFunctionPost(String ref, Map<String, Object> requestBody,) async {
    final response = await executeProjectFunctionApiProjectsRefExecuteFunctionPostWithHttpInfo(ref, requestBody,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      final responseBody = await _decodeBodyBytes(response);
      return (await apiClient.deserializeAsync(responseBody, 'List<Map<String, Object>>') as List)
        .cast<Map<String, Object>>()
        .toList(growable: false);

    }
    return null;
  }

  /// Get Project Ai Functions
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> getProjectAiFunctionsApiProjectsRefFunctionsGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/functions'
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

  /// Get Project Ai Functions
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<List<ProjectAIFunctionItem>?> getProjectAiFunctionsApiProjectsRefFunctionsGet(String ref,) async {
    final response = await getProjectAiFunctionsApiProjectsRefFunctionsGetWithHttpInfo(ref,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      final responseBody = await _decodeBodyBytes(response);
      return (await apiClient.deserializeAsync(responseBody, 'List<ProjectAIFunctionItem>') as List)
        .cast<ProjectAIFunctionItem>()
        .toList(growable: false);

    }
    return null;
  }

  /// Get Project S3 Vector Keys
  ///
  /// Return the selected tenant's SigV4 pair to an authorized Studio admin.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> getProjectS3VectorKeysApiProjectsProjectRefStorageS3KeysGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/storage/s3-keys'
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

  /// Get Project S3 Vector Keys
  ///
  /// Return the selected tenant's SigV4 pair to an authorized Studio admin.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<ProjectS3VectorKeysResponse?> getProjectS3VectorKeysApiProjectsProjectRefStorageS3KeysGet(String projectRef,) async {
    final response = await getProjectS3VectorKeysApiProjectsProjectRefStorageS3KeysGetWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ProjectS3VectorKeysResponse',) as ProjectS3VectorKeysResponse;
    
    }
    return null;
  }

  /// Get Project User Telemetry
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [String] period:
  ///
  /// * [DateTime] start:
  ///
  /// * [DateTime] end:
  Future<Response> getProjectUserTelemetryApiProjectsProjectRefTelemetryUsersGetWithHttpInfo(String projectRef, { String? period, DateTime? start, DateTime? end, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/telemetry/users'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (period != null) {
      queryParams.addAll(_queryParams('', 'period', period));
    }
    if (start != null) {
      queryParams.addAll(_queryParams('', 'start', start));
    }
    if (end != null) {
      queryParams.addAll(_queryParams('', 'end', end));
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

  /// Get Project User Telemetry
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [String] period:
  ///
  /// * [DateTime] start:
  ///
  /// * [DateTime] end:
  Future<ProjectUserTelemetryResponse?> getProjectUserTelemetryApiProjectsProjectRefTelemetryUsersGet(String projectRef, { String? period, DateTime? start, DateTime? end, }) async {
    final response = await getProjectUserTelemetryApiProjectsProjectRefTelemetryUsersGetWithHttpInfo(projectRef,  period: period, start: start, end: end, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ProjectUserTelemetryResponse',) as ProjectUserTelemetryResponse;
    
    }
    return null;
  }

  /// Get Projects For User
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [Map<String, String>] requestBody (required):
  Future<Response> getProjectsForUserApiAdminProjectsInfoPostWithHttpInfo(Map<String, String> requestBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/admin/projects-info';

    // ignore: prefer_final_locals
    Object? postBody = requestBody;

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

  /// Get Projects For User
  ///
  /// Parameters:
  ///
  /// * [Map<String, String>] requestBody (required):
  Future<ProjectsInfoResponse?> getProjectsForUserApiAdminProjectsInfoPost(Map<String, String> requestBody,) async {
    final response = await getProjectsForUserApiAdminProjectsInfoPostWithHttpInfo(requestBody,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ProjectsInfoResponse',) as ProjectsInfoResponse;
    
    }
    return null;
  }

  /// List All Users For Admin
  ///
  /// Lista todos os usuários disponíveis para admins. Como a API não tem acesso ao cache, retorna uma estrutura que o Nginx pode completar ou usa proxy para Nginx.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> listAllUsersForAdminApiAdminProjectsProjectRefAllUsersGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/admin/projects/{project_ref}/all-users'
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

  /// List All Users For Admin
  ///
  /// Lista todos os usuários disponíveis para admins. Como a API não tem acesso ao cache, retorna uma estrutura que o Nginx pode completar ou usa proxy para Nginx.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<AllUsersResponse?> listAllUsersForAdminApiAdminProjectsProjectRefAllUsersGet(String projectRef,) async {
    final response = await listAllUsersForAdminApiAdminProjectsProjectRefAllUsersGetWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'AllUsersResponse',) as AllUsersResponse;
    
    }
    return null;
  }

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Response> proxyProjectMetaDeleteWithHttpInfo(String ref, { String? metaPath, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (metaPath != null) {
      queryParams.addAll(_queryParams('', 'meta_path', metaPath));
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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Object?> proxyProjectMetaDelete(String ref, { String? metaPath, }) async {
    final response = await proxyProjectMetaDeleteWithHttpInfo(ref,  metaPath: metaPath, );
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Response> proxyProjectMetaGetWithHttpInfo(String ref, { String? metaPath, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (metaPath != null) {
      queryParams.addAll(_queryParams('', 'meta_path', metaPath));
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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Object?> proxyProjectMetaGet(String ref, { String? metaPath, }) async {
    final response = await proxyProjectMetaGetWithHttpInfo(ref,  metaPath: metaPath, );
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Response> proxyProjectMetaPatchWithHttpInfo(String ref, { String? metaPath, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (metaPath != null) {
      queryParams.addAll(_queryParams('', 'meta_path', metaPath));
    }

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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Object?> proxyProjectMetaPatch(String ref, { String? metaPath, }) async {
    final response = await proxyProjectMetaPatchWithHttpInfo(ref,  metaPath: metaPath, );
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Response> proxyProjectMetaPathDeleteWithHttpInfo(String ref, String metaPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta/{meta_path}'
      .replaceAll('{ref}', ref)
      .replaceAll('{meta_path}', metaPath);

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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Object?> proxyProjectMetaPathDelete(String ref, String metaPath,) async {
    final response = await proxyProjectMetaPathDeleteWithHttpInfo(ref, metaPath,);
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Response> proxyProjectMetaPathGetWithHttpInfo(String ref, String metaPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta/{meta_path}'
      .replaceAll('{ref}', ref)
      .replaceAll('{meta_path}', metaPath);

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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Object?> proxyProjectMetaPathGet(String ref, String metaPath,) async {
    final response = await proxyProjectMetaPathGetWithHttpInfo(ref, metaPath,);
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Response> proxyProjectMetaPathPatchWithHttpInfo(String ref, String metaPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta/{meta_path}'
      .replaceAll('{ref}', ref)
      .replaceAll('{meta_path}', metaPath);

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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Object?> proxyProjectMetaPathPatch(String ref, String metaPath,) async {
    final response = await proxyProjectMetaPathPatchWithHttpInfo(ref, metaPath,);
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Response> proxyProjectMetaPathPostWithHttpInfo(String ref, String metaPath,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta/{meta_path}'
      .replaceAll('{ref}', ref)
      .replaceAll('{meta_path}', metaPath);

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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath (required):
  Future<Object?> proxyProjectMetaPathPost(String ref, String metaPath,) async {
    final response = await proxyProjectMetaPathPostWithHttpInfo(ref, metaPath,);
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

  /// Proxy Project Meta
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Response> proxyProjectMetaPostWithHttpInfo(String ref, { String? metaPath, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/meta'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (metaPath != null) {
      queryParams.addAll(_queryParams('', 'meta_path', metaPath));
    }

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

  /// Proxy Project Meta
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] metaPath:
  Future<Object?> proxyProjectMetaPost(String ref, { String? metaPath, }) async {
    final response = await proxyProjectMetaPostWithHttpInfo(ref,  metaPath: metaPath, );
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

  /// Transfer Project
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [TransferBody] transferBody (required):
  Future<Response> transferProjectApiProjectsProjectRefTransferPostWithHttpInfo(String projectRef, TransferBody transferBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/transfer'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody = transferBody;

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

  /// Transfer Project
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [TransferBody] transferBody (required):
  Future<TransferResponse?> transferProjectApiProjectsProjectRefTransferPost(String projectRef, TransferBody transferBody,) async {
    final response = await transferProjectApiProjectsProjectRefTransferPostWithHttpInfo(projectRef, transferBody,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'TransferResponse',) as TransferResponse;
    
    }
    return null;
  }
}
