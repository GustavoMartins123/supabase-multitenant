//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class ClientConfigurationApi {
  ClientConfigurationApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Get Client Configuration
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] applicationRef (required):
  Future<Response> getClientConfigurationConfigApplicationRefGetWithHttpInfo(String applicationRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/config/{application_ref}'
      .replaceAll('{application_ref}', applicationRef);

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

  /// Get Client Configuration
  ///
  /// Parameters:
  ///
  /// * [String] applicationRef (required):
  Future<ClientConfigurationResponse?> getClientConfigurationConfigApplicationRefGet(String applicationRef,) async {
    final response = await getClientConfigurationConfigApplicationRefGetWithHttpInfo(applicationRef,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'ClientConfigurationResponse',) as ClientConfigurationResponse;

    }
    return null;
  }
}
