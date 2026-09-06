//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class OpaqueApiKeysApi {
  OpaqueApiKeysApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Abort Opaque Api Key Migration
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDeleteWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/opaque-api-keys/migration'
      .replaceAll('{project_name}', projectName);

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

  /// Abort Opaque Api Key Migration
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<MigrationAbortResponse?> abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDelete(String projectName,) async {
    final response = await abortOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationDeleteWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'MigrationAbortResponse',) as MigrationAbortResponse;
    
    }
    return null;
  }

  /// Activate Api Key Slot
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPostWithHttpInfo(String projectName, String slotId, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots/{slot_id}/activation'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{slot_id}', slotId);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'X-Step-Up-Token'] = parameterToString(xStepUpToken);
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

  /// Activate Api Key Slot
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<SlotActivationResponse?> activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPost(String projectName, String slotId, { String? xStepUpToken, }) async {
    final response = await activateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdActivationPostWithHttpInfo(projectName, slotId,  xStepUpToken: xStepUpToken, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'SlotActivationResponse',) as SlotActivationResponse;
    
    }
    return null;
  }

  /// Cancel Api Key Slot Rotation
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  Future<Response> cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDeleteWithHttpInfo(String projectName, String slotId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots/{slot_id}/rotation'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{slot_id}', slotId);

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

  /// Cancel Api Key Slot Rotation
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  Future<SlotCancelResponse?> cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDelete(String projectName, String slotId,) async {
    final response = await cancelApiKeySlotRotationApiProjectsProjectNameApiKeySlotsSlotIdRotationDeleteWithHttpInfo(projectName, slotId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'SlotCancelResponse',) as SlotCancelResponse;
    
    }
    return null;
  }

  /// Claim Api Key
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] keyId (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPostWithHttpInfo(String projectName, String keyId, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-reveals/{key_id}/claim'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{key_id}', keyId);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'X-Step-Up-Token'] = parameterToString(xStepUpToken);
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

  /// Claim Api Key
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] keyId (required):
  ///
  /// * [String] xStepUpToken:
  Future<RevealClaimResponse?> claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPost(String projectName, String keyId, { String? xStepUpToken, }) async {
    final response = await claimApiKeyApiProjectsProjectNameApiKeyRevealsKeyIdClaimPostWithHttpInfo(projectName, keyId,  xStepUpToken: xStepUpToken, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RevealClaimResponse',) as RevealClaimResponse;
    
    }
    return null;
  }

  /// Confirm Api Key Slot Installation
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [ConfirmApiKeyInstallation] confirmApiKeyInstallation (required):
  Future<Response> confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPostWithHttpInfo(String projectName, String slotId, ConfirmApiKeyInstallation confirmApiKeyInstallation,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots/{slot_id}/rotation-confirmation'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{slot_id}', slotId);

    // ignore: prefer_final_locals
    Object? postBody = confirmApiKeyInstallation;

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

  /// Confirm Api Key Slot Installation
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [ConfirmApiKeyInstallation] confirmApiKeyInstallation (required):
  Future<SlotConfirmResponse?> confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPost(String projectName, String slotId, ConfirmApiKeyInstallation confirmApiKeyInstallation,) async {
    final response = await confirmApiKeySlotInstallationApiProjectsProjectNameApiKeySlotsSlotIdRotationConfirmationPostWithHttpInfo(projectName, slotId, confirmApiKeyInstallation,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'SlotConfirmResponse',) as SlotConfirmResponse;
    
    }
    return null;
  }

  /// Create Api Key Slot
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [CreateApiKeySlot] createApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> createApiKeySlotApiProjectsProjectNameApiKeySlotsPostWithHttpInfo(String projectName, CreateApiKeySlot createApiKeySlot, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = createApiKeySlot;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'X-Step-Up-Token'] = parameterToString(xStepUpToken);
    }

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

  /// Create Api Key Slot
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [CreateApiKeySlot] createApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<IssuedKeyResponse?> createApiKeySlotApiProjectsProjectNameApiKeySlotsPost(String projectName, CreateApiKeySlot createApiKeySlot, { String? xStepUpToken, }) async {
    final response = await createApiKeySlotApiProjectsProjectNameApiKeySlotsPostWithHttpInfo(projectName, createApiKeySlot,  xStepUpToken: xStepUpToken, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'IssuedKeyResponse',) as IssuedKeyResponse;
    
    }
    return null;
  }

  /// Cutover Opaque Api Key Migration
  ///
  /// Stop legacy ingress, activate confirmed keys, and start opaque-only.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPostWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/opaque-api-keys/migration/cutover'
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

  /// Cutover Opaque Api Key Migration
  ///
  /// Stop legacy ingress, activate confirmed keys, and start opaque-only.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<MigrationCutoverResponse?> cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPost(String projectName,) async {
    final response = await cutoverOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationCutoverPostWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'MigrationCutoverResponse',) as MigrationCutoverResponse;
    
    }
    return null;
  }

  /// Get Api Key Reveals
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-reveals'
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

  /// Get Api Key Reveals
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<RevealListResponse?> getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGet(String projectName,) async {
    final response = await getApiKeyRevealsApiProjectsProjectNameApiKeyRevealsGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RevealListResponse',) as RevealListResponse;
    
    }
    return null;
  }

  /// Get Api Key Slots
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> getApiKeySlotsApiProjectsProjectNameApiKeySlotsGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots'
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

  /// Get Api Key Slots
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<SlotListResponse?> getApiKeySlotsApiProjectsProjectNameApiKeySlotsGet(String projectName,) async {
    final response = await getApiKeySlotsApiProjectsProjectNameApiKeySlotsGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'SlotListResponse',) as SlotListResponse;
    
    }
    return null;
  }

  /// Get Opaque Api Key Migration
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGetWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/opaque-api-keys/migration'
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

  /// Get Opaque Api Key Migration
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<MigrationStatusResponse?> getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGet(String projectName,) async {
    final response = await getOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationGetWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'MigrationStatusResponse',) as MigrationStatusResponse;
    
    }
    return null;
  }

  /// Prepare Opaque Api Key Migration
  ///
  /// Prepare rejected opaque keys without changing the running gateway.
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<Response> prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePostWithHttpInfo(String projectName,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/opaque-api-keys/migration/prepare'
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

  /// Prepare Opaque Api Key Migration
  ///
  /// Prepare rejected opaque keys without changing the running gateway.
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  Future<MigrationPrepareResponse?> prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePost(String projectName,) async {
    final response = await prepareOpaqueApiKeyMigrationApiProjectsProjectNameOpaqueApiKeysMigrationPreparePostWithHttpInfo(projectName,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'MigrationPrepareResponse',) as MigrationPrepareResponse;
    
    }
    return null;
  }

  /// Revoke Api Key Slot
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  Future<Response> revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDeleteWithHttpInfo(String projectName, String slotId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots/{slot_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{slot_id}', slotId);

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

  /// Revoke Api Key Slot
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  Future<SlotRevokeResponse?> revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDelete(String projectName, String slotId,) async {
    final response = await revokeApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdDeleteWithHttpInfo(projectName, slotId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'SlotRevokeResponse',) as SlotRevokeResponse;
    
    }
    return null;
  }

  /// Rotate Api Key Slot
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [RotateApiKeySlot] rotateApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPostWithHttpInfo(String projectName, String slotId, RotateApiKeySlot rotateApiKeySlot, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots/{slot_id}/rotation'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{slot_id}', slotId);

    // ignore: prefer_final_locals
    Object? postBody = rotateApiKeySlot;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'X-Step-Up-Token'] = parameterToString(xStepUpToken);
    }

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

  /// Rotate Api Key Slot
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [RotateApiKeySlot] rotateApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<IssuedKeyResponse?> rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPost(String projectName, String slotId, RotateApiKeySlot rotateApiKeySlot, { String? xStepUpToken, }) async {
    final response = await rotateApiKeySlotApiProjectsProjectNameApiKeySlotsSlotIdRotationPostWithHttpInfo(projectName, slotId, rotateApiKeySlot,  xStepUpToken: xStepUpToken, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'IssuedKeyResponse',) as IssuedKeyResponse;
    
    }
    return null;
  }

  /// Update Api Key Slot Policy
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [UpdateApiKeySlotPolicy] updateApiKeySlotPolicy (required):
  Future<Response> updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatchWithHttpInfo(String projectName, String slotId, UpdateApiKeySlotPolicy updateApiKeySlotPolicy,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/api-key-slots/{slot_id}'
      .replaceAll('{project_name}', projectName)
      .replaceAll('{slot_id}', slotId);

    // ignore: prefer_final_locals
    Object? postBody = updateApiKeySlotPolicy;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    const contentTypes = <String>['application/json'];


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

  /// Update Api Key Slot Policy
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [UpdateApiKeySlotPolicy] updateApiKeySlotPolicy (required):
  Future<SlotPolicyUpdateResponse?> updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatch(String projectName, String slotId, UpdateApiKeySlotPolicy updateApiKeySlotPolicy,) async {
    final response = await updateApiKeySlotPolicyApiProjectsProjectNameApiKeySlotsSlotIdPatchWithHttpInfo(projectName, slotId, updateApiKeySlotPolicy,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'SlotPolicyUpdateResponse',) as SlotPolicyUpdateResponse;
    
    }
    return null;
  }
}
