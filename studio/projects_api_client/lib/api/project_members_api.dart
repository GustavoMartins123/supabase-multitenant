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
  /// * [String] projectRef (required):
  ///
  /// * [AddMember] addMember (required):
  Future<Response> addMemberApiProjectsProjectRefMembersPostWithHttpInfo(String projectRef, AddMember addMember,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/members'
      .replaceAll('{project_ref}', projectRef);

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
  /// * [String] projectRef (required):
  ///
  /// * [AddMember] addMember (required):
  Future<AddMemberResponse?> addMemberApiProjectsProjectRefMembersPost(String projectRef, AddMember addMember,) async {
    final response = await addMemberApiProjectsProjectRefMembersPostWithHttpInfo(projectRef, addMember,);
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

  /// List Available Project Users
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [bool] includeMembers:
  ///
  /// * [String] mode:
  Future<Response> listAvailableProjectUsersApiProjectsProjectRefAvailableUsersGetWithHttpInfo(String projectRef, { bool? includeMembers, String? mode, }) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/available-users'
      .replaceAll('{project_ref}', projectRef);

    // ignore: prefer_final_locals
    Object? postBody;

    final queryParams = <QueryParam>[];
    final headerParams = <String, String>{};
    final formParams = <String, String>{};

    if (includeMembers != null) {
      queryParams.addAll(_queryParams('', 'include_members', includeMembers));
    }
    if (mode != null) {
      queryParams.addAll(_queryParams('', 'mode', mode));
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

  /// List Available Project Users
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  ///
  /// * [bool] includeMembers:
  ///
  /// * [String] mode:
  Future<List<AvailableProjectUser>?> listAvailableProjectUsersApiProjectsProjectRefAvailableUsersGet(String projectRef, { bool? includeMembers, String? mode, }) async {
    final response = await listAvailableProjectUsersApiProjectsProjectRefAvailableUsersGetWithHttpInfo(projectRef,  includeMembers: includeMembers, mode: mode, );
    if (response.statusCode >= HttpStatus.badRequest) {
      throw ApiException(response.statusCode, await _decodeBodyBytes(response));
    }
    // When a remote server returns no body with a status of 204, we shall not decode it.
    // At the time of writing this, `dart:convert` will throw an "Unexpected end of input"
    // FormatException when trying to decode an empty string.
    if (response.body.isNotEmpty && response.statusCode != HttpStatus.noContent) {
      final responseBody = await _decodeBodyBytes(response);
      return (await apiClient.deserializeAsync(responseBody, 'List<AvailableProjectUser>') as List)
        .cast<AvailableProjectUser>()
        .toList(growable: false);

    }
    return null;
  }

  /// List Members By Ref
  ///
  /// Note: This method returns the HTTP [Response].
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<Response> listMembersByRefApiProjectsProjectRefMembersGetWithHttpInfo(String projectRef,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/members'
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

  /// List Members By Ref
  ///
  /// Parameters:
  ///
  /// * [String] projectRef (required):
  Future<List<MemberItem>?> listMembersByRefApiProjectsProjectRefMembersGet(String projectRef,) async {
    final response = await listMembersByRefApiProjectsProjectRefMembersGetWithHttpInfo(projectRef,);
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
  /// * [String] projectRef (required):
  ///
  /// * [String] memberId (required):
  Future<Response> removeMemberByRefApiProjectsProjectRefMembersMemberIdDeleteWithHttpInfo(String projectRef, String memberId,) async {
    // ignore: prefer_const_declarations
    final path = r'/api/projects/{project_ref}/members/{member_id}'
      .replaceAll('{project_ref}', projectRef)
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
  /// * [String] projectRef (required):
  ///
  /// * [String] memberId (required):
  Future<RemoveMemberResponse?> removeMemberByRefApiProjectsProjectRefMembersMemberIdDelete(String projectRef, String memberId,) async {
    final response = await removeMemberByRefApiProjectsProjectRefMembersMemberIdDeleteWithHttpInfo(projectRef, memberId,);
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
