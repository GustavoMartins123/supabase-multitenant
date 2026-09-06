//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;


class ProjectMembersApi {
  ProjectMembersApi([ApiClient? apiClient]) : apiClient = apiClient ?? defaultApiClient;

  final ApiClient apiClient;

  /// Add Member
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [AddMember] addMember (required):
  Future<Response> addMemberApiProjectsProjectNameMembersPostWithHttpInfo(String projectName, AddMember addMember,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_name}/members'
      .replaceAll('{project_name}', projectName);

    // ignore: prefer_final_locals
    Object? postBody = addMember;

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

  /// Add Member
  ///
  /// Parameters:
  ///
  /// * [String] projectName (required):
  ///
  /// * [AddMember] addMember (required):
  Future<AddMemberResponse?> addMemberApiProjectsProjectNameMembersPost(String projectName, AddMember addMember,) async {
    final response = await addMemberApiProjectsProjectNameMembersPostWithHttpInfo(projectName, addMember,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'AddMemberResponse',) as AddMemberResponse;
    
    }
    return null;
  }

  /// List Members By Ref
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] name (required):
  Future<Response> listMembersByRefApiProjectsNameMembersGetWithHttpInfo(String name,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{name}/members'
      .replaceAll('{name}', name);

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

  /// List Members By Ref
  ///
  /// Parameters:
  ///
  /// * [String] name (required):
  Future<List<MemberItem>?> listMembersByRefApiProjectsNameMembersGet(String name,) async {
    final response = await listMembersByRefApiProjectsNameMembersGetWithHttpInfo(name,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      final responseBody = await _decodeBodyBytes(response);
      return (await apiClient.deserializeAsync(responseBody, 'List<MemberItem>') as List)
        .cast<MemberItem>()
        .toList(growable: false);

    }
    return null;
  }

  /// Remove Member By Ref
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] name (required):
  ///
  /// * [String] memberId (required):
  Future<Response> removeMemberByRefApiProjectsNameMembersMemberIdDeleteWithHttpInfo(String name, String memberId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{name}/members/{member_id}'
      .replaceAll('{name}', name)
      .replaceAll('{member_id}', memberId);

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

  /// Remove Member By Ref
  ///
  /// Parameters:
  ///
  /// * [String] name (required):
  ///
  /// * [String] memberId (required):
  Future<RemoveMemberResponse?> removeMemberByRefApiProjectsNameMembersMemberIdDelete(String name, String memberId,) async {
    final response = await removeMemberByRefApiProjectsNameMembersMemberIdDeleteWithHttpInfo(name, memberId,);
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      return await apiClient.deserializeAsync(await _decodeBodyBytes(response), 'RemoveMemberResponse',) as RemoveMemberResponse;
    
    }
    return null;
  }
}
