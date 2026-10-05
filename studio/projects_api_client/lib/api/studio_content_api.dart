//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class StudioContentApi {
  StudioContentApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Content Count
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> contentCountApiProjectsRefContentCountGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/count'
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

  /// Content Count
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> contentCountApiProjectsRefContentCountGet(String ref,) async {
    final response = await contentCountApiProjectsRefContentCountGetWithHttpInfo(ref,);
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

  /// Content Delete
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> contentDeleteApiProjectsRefContentDeleteWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content'
      .replaceAll('{ref}', ref);

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

  /// Content Delete
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> contentDeleteApiProjectsRefContentDelete(String ref,) async {
    final response = await contentDeleteApiProjectsRefContentDeleteWithHttpInfo(ref,);
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

  /// Content Item
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] id (required):
  Future<Response> contentItemApiProjectsRefContentItemIdGetWithHttpInfo(String ref, String id,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/item/{id}'
      .replaceAll('{ref}', ref)
      .replaceAll('{id}', id);

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

  /// Content Item
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] id (required):
  Future<Object?> contentItemApiProjectsRefContentItemIdGet(String ref, String id,) async {
    final response = await contentItemApiProjectsRefContentItemIdGetWithHttpInfo(ref, id,);
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

  /// Content List
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> contentListApiProjectsRefContentGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content'
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

  /// Content List
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> contentListApiProjectsRefContentGet(String ref,) async {
    final response = await contentListApiProjectsRefContentGetWithHttpInfo(ref,);
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

  /// Content Save
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [SnippetBody] snippetBody (required):
  Future<Response> contentSaveApiProjectsRefContentPutWithHttpInfo(String ref, SnippetBody snippetBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = snippetBody;

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

  /// Content Save
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [SnippetBody] snippetBody (required):
  Future<Object?> contentSaveApiProjectsRefContentPut(String ref, SnippetBody snippetBody,) async {
    final response = await contentSaveApiProjectsRefContentPutWithHttpInfo(ref, snippetBody,);
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

  /// Folder Create
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [FolderBody] folderBody (required):
  Future<Response> folderCreateApiProjectsRefContentFoldersPostWithHttpInfo(String ref, FolderBody folderBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/folders'
      .replaceAll('{ref}', ref);

    // ignore: prefer_final_locals
    Object? postBody = folderBody;

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

  /// Folder Create
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [FolderBody] folderBody (required):
  Future<Object?> folderCreateApiProjectsRefContentFoldersPost(String ref, FolderBody folderBody,) async {
    final response = await folderCreateApiProjectsRefContentFoldersPostWithHttpInfo(ref, folderBody,);
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

  /// Folder Item
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] id (required):
  Future<Response> folderItemApiProjectsRefContentFoldersIdGetWithHttpInfo(String ref, String id,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/folders/{id}'
      .replaceAll('{ref}', ref)
      .replaceAll('{id}', id);

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

  /// Folder Item
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] id (required):
  Future<Object?> folderItemApiProjectsRefContentFoldersIdGet(String ref, String id,) async {
    final response = await folderItemApiProjectsRefContentFoldersIdGetWithHttpInfo(ref, id,);
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

  /// Folder Update
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] id (required):
  ///
  /// * [FolderBody] folderBody (required):
  Future<Response> folderUpdateApiProjectsRefContentFoldersIdPatchWithHttpInfo(String ref, String id, FolderBody folderBody,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/folders/{id}'
      .replaceAll('{ref}', ref)
      .replaceAll('{id}', id);

    // ignore: prefer_final_locals
    Object? postBody = folderBody;

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

  /// Folder Update
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  ///
  /// * [String] id (required):
  ///
  /// * [FolderBody] folderBody (required):
  Future<Object?> folderUpdateApiProjectsRefContentFoldersIdPatch(String ref, String id, FolderBody folderBody,) async {
    final response = await folderUpdateApiProjectsRefContentFoldersIdPatchWithHttpInfo(ref, id, folderBody,);
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

  /// Folders Delete
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> foldersDeleteApiProjectsRefContentFoldersDeleteWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/folders'
      .replaceAll('{ref}', ref);

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

  /// Folders Delete
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> foldersDeleteApiProjectsRefContentFoldersDelete(String ref,) async {
    final response = await foldersDeleteApiProjectsRefContentFoldersDeleteWithHttpInfo(ref,);
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

  /// Folders List
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Response> foldersListApiProjectsRefContentFoldersGetWithHttpInfo(String ref,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{ref}/content/folders'
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

  /// Folders List
  ///
  /// Parameters:
  ///
  /// * [String] ref (required):
  Future<Object?> foldersListApiProjectsRefContentFoldersGet(String ref,) async {
    final response = await foldersListApiProjectsRefContentFoldersGetWithHttpInfo(ref,);
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
