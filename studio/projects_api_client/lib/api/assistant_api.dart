//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class AssistantApi {
  AssistantApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Assistant Context
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> assistantContextApiProjectsRefAssistantContextGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/context'
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

  /// Assistant Context
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> assistantContextApiProjectsRefAssistantContextGet(String ref,) async {
    final response = await assistantContextApiProjectsRefAssistantContextGetWithHttpInfo(ref,);
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

  /// Assistant Execute
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [Map<String, Object>] requestBody (required):
  Future<Response> assistantExecuteApiProjectsRefAssistantExecutePostWithHttpInfo(String ref, Map<String, Object> requestBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/execute'
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

  /// Assistant Execute
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [Map<String, Object>] requestBody (required):
  Future<Object?> assistantExecuteApiProjectsRefAssistantExecutePost(String ref, Map<String, Object> requestBody,) async {
    final response = await assistantExecuteApiProjectsRefAssistantExecutePostWithHttpInfo(ref, requestBody,);
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

  /// Assistant Functions
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> assistantFunctionsApiProjectsRefAssistantFunctionsGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/functions'
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

  /// Assistant Functions
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> assistantFunctionsApiProjectsRefAssistantFunctionsGet(String ref,) async {
    final response = await assistantFunctionsApiProjectsRefAssistantFunctionsGetWithHttpInfo(ref,);
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

  /// Assistant Privileges
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [PrivilegeChangeBody] privilegeChangeBody (required):
  Future<Response> assistantPrivilegesApiProjectsRefAssistantPrivilegesPostWithHttpInfo(String ref, PrivilegeChangeBody privilegeChangeBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/privileges'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = privilegeChangeBody;

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

  /// Assistant Privileges
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [PrivilegeChangeBody] privilegeChangeBody (required):
  Future<Object?> assistantPrivilegesApiProjectsRefAssistantPrivilegesPost(String ref, PrivilegeChangeBody privilegeChangeBody,) async {
    final response = await assistantPrivilegesApiProjectsRefAssistantPrivilegesPostWithHttpInfo(ref, privilegeChangeBody,);
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

  /// Assistant Rows
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [ReadRowsBody] readRowsBody (required):
  Future<Response> assistantRowsApiProjectsRefAssistantRowsPostWithHttpInfo(String ref, ReadRowsBody readRowsBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/rows'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = readRowsBody;

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

  /// Assistant Rows
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [ReadRowsBody] readRowsBody (required):
  Future<Object?> assistantRowsApiProjectsRefAssistantRowsPost(String ref, ReadRowsBody readRowsBody,) async {
    final response = await assistantRowsApiProjectsRefAssistantRowsPostWithHttpInfo(ref, readRowsBody,);
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

  /// Assistant Schema
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> assistantSchemaApiProjectsRefAssistantSchemaGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/schema'
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

  /// Assistant Schema
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> assistantSchemaApiProjectsRefAssistantSchemaGet(String ref,) async {
    final response = await assistantSchemaApiProjectsRefAssistantSchemaGetWithHttpInfo(ref,);
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

  /// Assistant Security
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [SecurityBody] securityBody (required):
  Future<Response> assistantSecurityApiProjectsRefAssistantSecurityPostWithHttpInfo(String ref, SecurityBody securityBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/security'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = securityBody;

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

  /// Assistant Security
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [SecurityBody] securityBody (required):
  Future<Object?> assistantSecurityApiProjectsRefAssistantSecurityPost(String ref, SecurityBody securityBody,) async {
    final response = await assistantSecurityApiProjectsRefAssistantSecurityPostWithHttpInfo(ref, securityBody,);
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

  /// Assistant Sql
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [ExecuteSqlBody] executeSqlBody (required):
  Future<Response> assistantSqlApiProjectsRefAssistantSqlPostWithHttpInfo(String ref, ExecuteSqlBody executeSqlBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/assistant/sql'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = executeSqlBody;

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

  /// Assistant Sql
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [ExecuteSqlBody] executeSqlBody (required):
  Future<Object?> assistantSqlApiProjectsRefAssistantSqlPost(String ref, ExecuteSqlBody executeSqlBody,) async {
    final response = await assistantSqlApiProjectsRefAssistantSqlPostWithHttpInfo(ref, executeSqlBody,);
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
