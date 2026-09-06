//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class JobsApi {
  JobsApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// List Job History
  ///
  /// Lista o historico duravel de jobs visivel para o usuario autenticado.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectUuid:
  ///
  /// * [String] action:
  ///
  /// * [String] status:
  ///
  /// * [int] limit:
  ///
  /// * [int] offset:
  Future<Response> listJobHistoryApiJobsGetWithHttpInfo({ String? projectUuid, String? action, String? status, int? limit, int? offset, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/jobs';

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (projectUuid != null) {
      queryParams.addAll(_queryParams('', 'project_uuid', projectUuid));
    }
    if (action != null) {
      queryParams.addAll(_queryParams('', 'action', action));
    }
    if (status != null) {
      queryParams.addAll(_queryParams('', 'status', status));
    }
    if (limit != null) {
      queryParams.addAll(_queryParams('', 'limit', limit));
    }
    if (offset != null) {
      queryParams.addAll(_queryParams('', 'offset', offset));
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

  /// List Job History
  ///
  /// Lista o historico duravel de jobs visivel para o usuario autenticado.
  ///
  /// Parameters:
  ///
  /// * [String] projectUuid:
  ///
  /// * [String] action:
  ///
  /// * [String] status:
  ///
  /// * [int] limit:
  ///
  /// * [int] offset:
  Future<JobListResponse?> listJobHistoryApiJobsGet({ String? projectUuid, String? action, String? status, int? limit, int? offset, }) async {
    final response = await listJobHistoryApiJobsGetWithHttpInfo( projectUuid: projectUuid, action: action, status: status, limit: limit, offset: offset, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'JobListResponse',) as JobListResponse;
    
    }
    return null;
  }

  /// Project Status
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] jobId (required):
  Future<Response> projectStatusApiProjectsStatusJobIdGetWithHttpInfo(String jobId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/status/{job_id}'
      .replaceAll('{job_id}', jobId);

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

  /// Project Status
  ///
  /// Parameters:
  ///
  /// * [String] jobId (required):
  Future<JobResponse?> projectStatusApiProjectsStatusJobIdGet(String jobId,) async {
    final response = await projectStatusApiProjectsStatusJobIdGetWithHttpInfo(jobId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'JobResponse',) as JobResponse;
    
    }
    return null;
  }

  /// Retry Project Job
  ///
  /// Cria uma nova tentativa apenas para acoes explicitamente idempotentes.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] jobId (required):
  Future<Response> retryProjectJobApiJobsJobIdRetryPostWithHttpInfo(String jobId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/jobs/{job_id}/retry'
      .replaceAll('{job_id}', jobId);

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

  /// Retry Project Job
  ///
  /// Cria uma nova tentativa apenas para acoes explicitamente idempotentes.
  ///
  /// Parameters:
  ///
  /// * [String] jobId (required):
  Future<JobRetryResponse?> retryProjectJobApiJobsJobIdRetryPost(String jobId,) async {
    final response = await retryProjectJobApiJobsJobIdRetryPostWithHttpInfo(jobId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'JobRetryResponse',) as JobRetryResponse;
    
    }
    return null;
  }
}
