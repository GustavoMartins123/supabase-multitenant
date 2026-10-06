//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class AccessPoliciesApi {
  AccessPoliciesApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Countries
  ///
  /// Note: This method returns the HTTP [Response].
  Future<Response> countriesApiProjectsCountriesGetWithHttpInfo() async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/countries';

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

  /// Countries
  Future<CountryCatalog?> countriesApiProjectsCountriesGet() async {
    final response = await countriesApiProjectsCountriesGetWithHttpInfo();
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'CountryCatalog',) as CountryCatalog;

    }
    return null;
  }

  /// Project Policy
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> projectPolicyApiProjectsProjectRefAccessPolicyGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/access-policy'
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

  /// Project Policy
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<PolicyResponse?> projectPolicyApiProjectsProjectRefAccessPolicyGet(String projectRef,) async {
    final response = await projectPolicyApiProjectsProjectRefAccessPolicyGetWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'PolicyResponse',) as PolicyResponse;

    }
    return null;
  }

  /// Slot Policy
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  Future<Response> slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGetWithHttpInfo(String projectRef, String slotId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}/access-policy'
      .replaceAll('{project_ref}', projectRef)
      .replaceAll('{slot_id}', slotId);

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

  /// Slot Policy
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  Future<PolicyResponse?> slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGet(String projectRef, String slotId,) async {
    final response = await slotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyGetWithHttpInfo(projectRef, slotId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'PolicyResponse',) as PolicyResponse;

    }
    return null;
  }

  /// Update Project Policy
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [PolicyUpdate] policyUpdate (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> updateProjectPolicyApiProjectsProjectRefAccessPolicyPutWithHttpInfo(String projectRef, PolicyUpdate policyUpdate, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/access-policy'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody = policyUpdate;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'x-step-up-token'] = parameterToString(xStepUpToken);
    }

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

  /// Update Project Policy
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [PolicyUpdate] policyUpdate (required):
  ///
  /// * [String] xStepUpToken:
  Future<PolicyResponse?> updateProjectPolicyApiProjectsProjectRefAccessPolicyPut(String projectRef, PolicyUpdate policyUpdate, { String? xStepUpToken, }) async {
    final response = await updateProjectPolicyApiProjectsProjectRefAccessPolicyPutWithHttpInfo(projectRef, policyUpdate,  xStepUpToken: xStepUpToken, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'PolicyResponse',) as PolicyResponse;

    }
    return null;
  }

  /// Update Slot Policy
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [PolicyUpdate] policyUpdate (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPutWithHttpInfo(String projectRef, String slotId, PolicyUpdate policyUpdate, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}/access-policy'
      .replaceAll('{project_ref}', projectRef)
      .replaceAll('{slot_id}', slotId);

    // ignore: prefer_final_locals
    Object? postBody = policyUpdate;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'x-step-up-token'] = parameterToString(xStepUpToken);
    }

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

  /// Update Slot Policy
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [PolicyUpdate] policyUpdate (required):
  ///
  /// * [String] xStepUpToken:
  Future<PolicyResponse?> updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPut(String projectRef, String slotId, PolicyUpdate policyUpdate, { String? xStepUpToken, }) async {
    final response = await updateSlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdAccessPolicyPutWithHttpInfo(projectRef, slotId, policyUpdate,  xStepUpToken: xStepUpToken, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'PolicyResponse',) as PolicyResponse;

    }
    return null;
  }

  /// Usage
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> usageApiProjectsProjectRefAccessUsageGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/access-usage'
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

  /// Usage
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<AccessUsageResponse?> usageApiProjectsProjectRefAccessUsageGet(String projectRef,) async {
    final response = await usageApiProjectsProjectRefAccessUsageGetWithHttpInfo(projectRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'AccessUsageResponse',) as AccessUsageResponse;

    }
    return null;
  }
}
