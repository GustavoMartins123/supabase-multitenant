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
  /// * [String] projectRef (required):
  Future<Response> abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDeleteWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/opaque-api-keys/migration'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  Future<MigrationAbortResponse?> abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDelete(String projectRef,) async {
    final response = await abortOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationDeleteWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPostWithHttpInfo(String projectRef, String slotId, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}/activation'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<SlotActivationResponse?> activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPost(String projectRef, String slotId, { String? xStepUpToken, }) async {
    final response = await activateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdActivationPostWithHttpInfo(projectRef, slotId,  xStepUpToken: xStepUpToken, );
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDeleteWithHttpInfo(String projectRef, String slotId, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}/rotation'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<SlotCancelResponse?> cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDelete(String projectRef, String slotId, { String? xStepUpToken, }) async {
    final response = await cancelApiKeySlotRotationApiProjectsProjectRefApiKeySlotsSlotIdRotationDeleteWithHttpInfo(projectRef, slotId,  xStepUpToken: xStepUpToken, );
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
  /// * [String] projectRef (required):
  ///
  /// * [String] keyId (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPostWithHttpInfo(String projectRef, String keyId, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-reveals/{key_id}/claim'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] keyId (required):
  ///
  /// * [String] xStepUpToken:
  Future<RevealClaimResponse?> claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPost(String projectRef, String keyId, { String? xStepUpToken, }) async {
    final response = await claimApiKeyApiProjectsProjectRefApiKeyRevealsKeyIdClaimPostWithHttpInfo(projectRef, keyId,  xStepUpToken: xStepUpToken, );
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [ConfirmApiKeyInstallation] confirmApiKeyInstallation (required):
  Future<Response> confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPostWithHttpInfo(String projectRef, String slotId, ConfirmApiKeyInstallation confirmApiKeyInstallation,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}/rotation-confirmation'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [ConfirmApiKeyInstallation] confirmApiKeyInstallation (required):
  Future<SlotConfirmResponse?> confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPost(String projectRef, String slotId, ConfirmApiKeyInstallation confirmApiKeyInstallation,) async {
    final response = await confirmApiKeySlotInstallationApiProjectsProjectRefApiKeySlotsSlotIdRotationConfirmationPostWithHttpInfo(projectRef, slotId, confirmApiKeyInstallation,);
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
  /// * [String] projectRef (required):
  ///
  /// * [CreateApiKeySlot] createApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> createApiKeySlotApiProjectsProjectRefApiKeySlotsPostWithHttpInfo(String projectRef, CreateApiKeySlot createApiKeySlot, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [CreateApiKeySlot] createApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<IssuedKeyResponse?> createApiKeySlotApiProjectsProjectRefApiKeySlotsPost(String projectRef, CreateApiKeySlot createApiKeySlot, { String? xStepUpToken, }) async {
    final response = await createApiKeySlotApiProjectsProjectRefApiKeySlotsPostWithHttpInfo(projectRef, createApiKeySlot,  xStepUpToken: xStepUpToken, );
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
  /// * [String] projectRef (required):
  Future<Response> cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPostWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/opaque-api-keys/migration/cutover'
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

  /// Cutover Opaque Api Key Migration
  ///
  /// Stop legacy ingress, activate confirmed keys, and start opaque-only.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<MigrationCutoverResponse?> cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPost(String projectRef,) async {
    final response = await cutoverOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationCutoverPostWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  Future<Response> getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-reveals'
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

  /// Get Api Key Reveals
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<RevealListResponse?> getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGet(String projectRef,) async {
    final response = await getApiKeyRevealsApiProjectsProjectRefApiKeyRevealsGetWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  Future<Response> getApiKeySlotsApiProjectsProjectRefApiKeySlotsGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots'
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

  /// Get Api Key Slots
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<SlotListResponse?> getApiKeySlotsApiProjectsProjectRefApiKeySlotsGet(String projectRef,) async {
    final response = await getApiKeySlotsApiProjectsProjectRefApiKeySlotsGetWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  Future<Response> getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/opaque-api-keys/migration'
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

  /// Get Opaque Api Key Migration
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<MigrationStatusResponse?> getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGet(String projectRef,) async {
    final response = await getOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationGetWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  Future<Response> prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePostWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/opaque-api-keys/migration/prepare'
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

  /// Prepare Opaque Api Key Migration
  ///
  /// Prepare rejected opaque keys without changing the running gateway.
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<MigrationPrepareResponse?> prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePost(String projectRef,) async {
    final response = await prepareOpaqueApiKeyMigrationApiProjectsProjectRefOpaqueApiKeysMigrationPreparePostWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDeleteWithHttpInfo(String projectRef, String slotId, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [String] xStepUpToken:
  Future<SlotRevokeResponse?> revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDelete(String projectRef, String slotId, { String? xStepUpToken, }) async {
    final response = await revokeApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdDeleteWithHttpInfo(projectRef, slotId,  xStepUpToken: xStepUpToken, );
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [RotateApiKeySlot] rotateApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPostWithHttpInfo(String projectRef, String slotId, RotateApiKeySlot rotateApiKeySlot, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}/rotation'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [RotateApiKeySlot] rotateApiKeySlot (required):
  ///
  /// * [String] xStepUpToken:
  Future<IssuedKeyResponse?> rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPost(String projectRef, String slotId, RotateApiKeySlot rotateApiKeySlot, { String? xStepUpToken, }) async {
    final response = await rotateApiKeySlotApiProjectsProjectRefApiKeySlotsSlotIdRotationPostWithHttpInfo(projectRef, slotId, rotateApiKeySlot,  xStepUpToken: xStepUpToken, );
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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [UpdateApiKeySlotPolicy] updateApiKeySlotPolicy (required):
  ///
  /// * [String] xStepUpToken:
  Future<Response> updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatchWithHttpInfo(String projectRef, String slotId, UpdateApiKeySlotPolicy updateApiKeySlotPolicy, { String? xStepUpToken, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/api-key-slots/{slot_id}'
      .replaceAll('{project_ref}', projectRef)
      .replaceAll('{slot_id}', slotId);

    // ignore: prefer_final_locals
    Object? postBody = updateApiKeySlotPolicy;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (xStepUpToken != null) {
      headerParams[r'X-Step-Up-Token'] = parameterToString(xStepUpToken);
    }

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
  /// * [String] projectRef (required):
  ///
  /// * [String] slotId (required):
  ///
  /// * [UpdateApiKeySlotPolicy] updateApiKeySlotPolicy (required):
  ///
  /// * [String] xStepUpToken:
  Future<SlotPolicyUpdateResponse?> updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatch(String projectRef, String slotId, UpdateApiKeySlotPolicy updateApiKeySlotPolicy, { String? xStepUpToken, }) async {
    final response = await updateApiKeySlotPolicyApiProjectsProjectRefApiKeySlotsSlotIdPatchWithHttpInfo(projectRef, slotId, updateApiKeySlotPolicy,  xStepUpToken: xStepUpToken, );
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
