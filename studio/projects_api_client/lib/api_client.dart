//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ApiClient {
  ApiClient({this.basePath = 'http://localhost', this.authentication,});

  final String basePath;
  final Authentication? authentication;

  var _client = Client();
  final _defaultHeaderMap = <String, String>{};

  /// Returns the current HTTP [Client] instance to use in this class.
  ///
  /// The return value is guaranteed to never be null.
  Client get client => _client;

  /// Requests to use a new HTTP [Client] in this class.
  set client(Client newClient) {
    _client = newClient;
  }

  Map<String, String> get defaultHeaderMap => _defaultHeaderMap;

  void addDefaultHeader(String key, String value) {
     _defaultHeaderMap[key] = value;
  }

  // We don't use a Map<String, String> for queryParams.
  // If collectionFormat is 'multi', a key might appear multiple times.
  Future<Response> invokeAPI(
    String path,
    String method,
    List<QueryParam> queryParams,
    Object? body,
    Map<String, String> headerParams,
    Map<String, String> formParams,
    String? contentType,
  ) async {
    await authentication?.applyToParams(queryParams, headerParams);

    headerParams.addAll(_defaultHeaderMap);
    if (contentType != null) {
      headerParams['Content-Type'] = contentType;
    }

    final urlEncodedQueryParams = queryParams.map((param) => '$param');
    final queryString = urlEncodedQueryParams.isNotEmpty ? '?${urlEncodedQueryParams.join('&')}' : '';
    final uri = Uri.parse('$basePath$path$queryString');

    try {
      // Special case for uploading a single file which isn't a 'multipart/form-data'.
      if (
        body is MultipartFile && (contentType == null ||
        !contentType.toLowerCase().startsWith('multipart/form-data'))
      ) {
        final request = StreamedRequest(method, uri);
        request.headers.addAll(headerParams);
        request.contentLength = body.length;
        body.finalize().listen(
          request.sink.add,
          onDone: request.sink.close,
          // ignore: avoid_types_on_closure_parameters
          onError: (Object error, StackTrace trace) => request.sink.close(),
          cancelOnError: true,
        );
        final response = await _client.send(request);
        return Response.fromStream(response);
      }

      if (body is MultipartRequest) {
        final request = MultipartRequest(method, uri);
        request.fields.addAll(body.fields);
        request.files.addAll(body.files);
        request.headers.addAll(body.headers);
        request.headers.addAll(headerParams);
        final response = await _client.send(request);
        return Response.fromStream(response);
      }

      final msgBody = contentType == 'application/x-www-form-urlencoded'
        ? formParams
        : await serializeAsync(body);
      final nullableHeaderParams = headerParams.isEmpty ? null : headerParams;

      switch(method) {
        case 'POST': return await _client.post(uri, headers: nullableHeaderParams, body: msgBody,);
        case 'PUT': return await _client.put(uri, headers: nullableHeaderParams, body: msgBody,);
        case 'DELETE': return await _client.delete(uri, headers: nullableHeaderParams, body: msgBody,);
        case 'PATCH': return await _client.patch(uri, headers: nullableHeaderParams, body: msgBody,);
        case 'HEAD': return await _client.head(uri, headers: nullableHeaderParams,);
        case 'GET': return await _client.get(uri, headers: nullableHeaderParams,);
      }
    } on SocketException catch (error, trace) {
      throw ApiException.withInner(
        HttpStatus.badRequest,
        'Socket operation failed: $method $path',
        error,
        trace,
      );
    } on TlsException catch (error, trace) {
      throw ApiException.withInner(
        HttpStatus.badRequest,
        'TLS/SSL communication failed: $method $path',
        error,
        trace,
      );
    } on IOException catch (error, trace) {
      throw ApiException.withInner(
        HttpStatus.badRequest,
        'I/O operation failed: $method $path',
        error,
        trace,
      );
    } on ClientException catch (error, trace) {
      throw ApiException.withInner(
        HttpStatus.badRequest,
        'HTTP connection failed: $method $path',
        error,
        trace,
      );
    } on Exception catch (error, trace) {
      throw ApiException.withInner(
        HttpStatus.badRequest,
        'Exception occurred: $method $path',
        error,
        trace,
      );
    }

    throw ApiException(
      HttpStatus.badRequest,
      'Invalid HTTP operation: $method $path',
    );
  }

  Future<dynamic> deserializeAsync(String value, String targetType, {bool growable = false,}) async =>
    // ignore: deprecated_member_use_from_same_package
    deserialize(value, targetType, growable: growable);

  @Deprecated('Scheduled for removal in OpenAPI Generator 6.x. Use deserializeAsync() instead.')
  dynamic deserialize(String value, String targetType, {bool growable = false,}) {
    // Remove all spaces. Necessary for regular expressions as well.
    targetType = targetType.replaceAll(' ', ''); // ignore: parameter_assignments

    // If the expected target type is String, nothing to do...
    return targetType == 'String'
      ? value
      : fromJson(json.decode(value), targetType, growable: growable);
  }

  // ignore: deprecated_member_use_from_same_package
  Future<String> serializeAsync(Object? value) async => serialize(value);

  @Deprecated('Scheduled for removal in OpenAPI Generator 6.x. Use serializeAsync() instead.')
  String serialize(Object? value) => value == null ? '' : json.encode(value);

  /// Returns a native instance of an OpenAPI class matching the [specified type][targetType].
  static dynamic fromJson(dynamic value, String targetType, {bool growable = false,}) {
    try {
      switch (targetType) {
        case 'String':
          return value is String ? value : value.toString();
        case 'int':
          return value is int ? value : int.parse('$value');
        case 'double':
          return value is double ? value : double.parse('$value');
        case 'bool':
          if (value is bool) {
            return value;
          }
          final valueString = '$value'.toLowerCase();
          return valueString == 'true' || valueString == '1';
        case 'DateTime':
          return value is DateTime ? value : DateTime.tryParse(value);
        case 'AddMember':
          return AddMember.fromJson(value);
        case 'AddMemberResponse':
          return AddMemberResponse.fromJson(value);
        case 'AllUsersMemberItem':
          return AllUsersMemberItem.fromJson(value);
        case 'AllUsersResponse':
          return AllUsersResponse.fromJson(value);
        case 'AssignProjectTagResponse':
          return AssignProjectTagResponse.fromJson(value);
        case 'AuthUserItem':
          return AuthUserItem.fromJson(value);
        case 'AuthUsersResponse':
          return AuthUsersResponse.fromJson(value);
        case 'AutomaticKeyRotationResponse':
          return AutomaticKeyRotationResponse.fromJson(value);
        case 'AutomaticKeyRotationUpdate':
          return AutomaticKeyRotationUpdate.fromJson(value);
        case 'CollaborationHintItem':
          return CollaborationHintItem.fromJson(value);
        case 'CollaborationMemberItem':
          return CollaborationMemberItem.fromJson(value);
        case 'CollaborationNoteItem':
          return CollaborationNoteItem.fromJson(value);
        case 'CollaborationNotificationItem':
          return CollaborationNotificationItem.fromJson(value);
        case 'CollaborationTagItem':
          return CollaborationTagItem.fromJson(value);
        case 'CollaborationThreadItem':
          return CollaborationThreadItem.fromJson(value);
        case 'ConfirmApiKeyInstallation':
          return ConfirmApiKeyInstallation.fromJson(value);
        case 'ContainerInfoItem':
          return ContainerInfoItem.fromJson(value);
        case 'ContainerLogsResponse':
          return ContainerLogsResponse.fromJson(value);
        case 'ContentIdentityResponse':
          return ContentIdentityResponse.fromJson(value);
        case 'CreateApiKeySlot':
          return CreateApiKeySlot.fromJson(value);
        case 'CreateProjectHintResponse':
          return CreateProjectHintResponse.fromJson(value);
        case 'CreateProjectNoteResponse':
          return CreateProjectNoteResponse.fromJson(value);
        case 'CreateRestorePointResponse':
          return CreateRestorePointResponse.fromJson(value);
        case 'CreateThreadMessageResponse':
          return CreateThreadMessageResponse.fromJson(value);
        case 'DeleteProjectNoteResponse':
          return DeleteProjectNoteResponse.fromJson(value);
        case 'DeleteRestorePointResponse':
          return DeleteRestorePointResponse.fromJson(value);
        case 'DuplicateProject':
          return DuplicateProject.fromJson(value);
        case 'EncKeyResponse':
          return EncKeyResponse.fromJson(value);
        case 'GetProjectCollaborationResponse':
          return GetProjectCollaborationResponse.fromJson(value);
        case 'GetProjectSettingsResponse':
          return GetProjectSettingsResponse.fromJson(value);
        case 'HTTPValidationError':
          return HTTPValidationError.fromJson(value);
        case 'IssuedKeyResponse':
          return IssuedKeyResponse.fromJson(value);
        case 'JobListResponse':
          return JobListResponse.fromJson(value);
        case 'JobResponse':
          return JobResponse.fromJson(value);
        case 'JobRetryResponse':
          return JobRetryResponse.fromJson(value);
        case 'KeyVersionResponse':
          return KeyVersionResponse.fromJson(value);
        case 'ListRestorePointsResponse':
          return ListRestorePointsResponse.fromJson(value);
        case 'LocationInner':
          return LocationInner.fromJson(value);
        case 'MemberItem':
          return MemberItem.fromJson(value);
        case 'MigrationAbortResponse':
          return MigrationAbortResponse.fromJson(value);
        case 'MigrationCutoverResponse':
          return MigrationCutoverResponse.fromJson(value);
        case 'MigrationPrepareResponse':
          return MigrationPrepareResponse.fromJson(value);
        case 'MigrationStatusResponse':
          return MigrationStatusResponse.fromJson(value);
        case 'ModelSource':
          return ModelSource.fromJson(value);
        case 'NewProject':
          return NewProject.fromJson(value);
        case 'ProjectAIFunctionItem':
          return ProjectAIFunctionItem.fromJson(value);
        case 'ProjectConfigTokenResponse':
          return ProjectConfigTokenResponse.fromJson(value);
        case 'ProjectDisplayNameUpdate':
          return ProjectDisplayNameUpdate.fromJson(value);
        case 'ProjectHintCreate':
          return ProjectHintCreate.fromJson(value);
        case 'ProjectHintStatusUpdate':
          return ProjectHintStatusUpdate.fromJson(value);
        case 'ProjectInfoItem':
          return ProjectInfoItem.fromJson(value);
        case 'ProjectListItem':
          return ProjectListItem.fromJson(value);
        case 'ProjectNoteCreate':
          return ProjectNoteCreate.fromJson(value);
        case 'ProjectNotificationRead':
          return ProjectNotificationRead.fromJson(value);
        case 'ProjectQueueInFlightJob':
          return ProjectQueueInFlightJob.fromJson(value);
        case 'ProjectQueueStatusResponse':
          return ProjectQueueStatusResponse.fromJson(value);
        case 'ProjectRenameHistoryResponse':
          return ProjectRenameHistoryResponse.fromJson(value);
        case 'ProjectRenameRequest':
          return ProjectRenameRequest.fromJson(value);
        case 'ProjectS3VectorKeysResponse':
          return ProjectS3VectorKeysResponse.fromJson(value);
        case 'ProjectStatusResponse':
          return ProjectStatusResponse.fromJson(value);
        case 'ProjectTagAssign':
          return ProjectTagAssign.fromJson(value);
        case 'ProjectThreadMessageCreate':
          return ProjectThreadMessageCreate.fromJson(value);
        case 'ProjectUserTelemetryResponse':
          return ProjectUserTelemetryResponse.fromJson(value);
        case 'ProjectsInfoResponse':
          return ProjectsInfoResponse.fromJson(value);
        case 'QueuedJobResponse':
          return QueuedJobResponse.fromJson(value);
        case 'RecreateProjectServicesResponse':
          return RecreateProjectServicesResponse.fromJson(value);
        case 'RecreateServices':
          return RecreateServices.fromJson(value);
        case 'RemoveMemberResponse':
          return RemoveMemberResponse.fromJson(value);
        case 'RenameHistoryEntry':
          return RenameHistoryEntry.fromJson(value);
        case 'RenameHistoryEvent':
          return RenameHistoryEvent.fromJson(value);
        case 'RenameProjectResponse':
          return RenameProjectResponse.fromJson(value);
        case 'RestartProjectResponse':
          return RestartProjectResponse.fromJson(value);
        case 'RestorePointCreate':
          return RestorePointCreate.fromJson(value);
        case 'RestorePointItem':
          return RestorePointItem.fromJson(value);
        case 'RestorePointsPermissions':
          return RestorePointsPermissions.fromJson(value);
        case 'RestoreRestorePointResponse':
          return RestoreRestorePointResponse.fromJson(value);
        case 'RevealClaimResponse':
          return RevealClaimResponse.fromJson(value);
        case 'RevealItem':
          return RevealItem.fromJson(value);
        case 'RevealListResponse':
          return RevealListResponse.fromJson(value);
        case 'RotateApiKeySlot':
          return RotateApiKeySlot.fromJson(value);
        case 'RotateProjectKeyResponse':
          return RotateProjectKeyResponse.fromJson(value);
        case 'SlotActivationResponse':
          return SlotActivationResponse.fromJson(value);
        case 'SlotCancelResponse':
          return SlotCancelResponse.fromJson(value);
        case 'SlotConfirmResponse':
          return SlotConfirmResponse.fromJson(value);
        case 'SlotItem':
          return SlotItem.fromJson(value);
        case 'SlotKeyItem':
          return SlotKeyItem.fromJson(value);
        case 'SlotListResponse':
          return SlotListResponse.fromJson(value);
        case 'SlotPolicyUpdateResponse':
          return SlotPolicyUpdateResponse.fromJson(value);
        case 'SlotRevokeResponse':
          return SlotRevokeResponse.fromJson(value);
        case 'StartProjectResponse':
          return StartProjectResponse.fromJson(value);
        case 'StopProjectResponse':
          return StopProjectResponse.fromJson(value);
        case 'StudioContextResponse':
          return StudioContextResponse.fromJson(value);
        case 'TelemetryUserItem':
          return TelemetryUserItem.fromJson(value);
        case 'TransferBody':
          return TransferBody.fromJson(value);
        case 'TransferResponse':
          return TransferResponse.fromJson(value);
        case 'UnassignProjectTagResponse':
          return UnassignProjectTagResponse.fromJson(value);
        case 'UpdateApiKeySlotPolicy':
          return UpdateApiKeySlotPolicy.fromJson(value);
        case 'UpdateDisplayNameResponse':
          return UpdateDisplayNameResponse.fromJson(value);
        case 'UpdateNotificationReadResponse':
          return UpdateNotificationReadResponse.fromJson(value);
        case 'UpdateProjectHintResponse':
          return UpdateProjectHintResponse.fromJson(value);
        case 'UpdateProjectSettingsResponse':
          return UpdateProjectSettingsResponse.fromJson(value);
        case 'UpdateSettings':
          return UpdateSettings.fromJson(value);
        case 'UserSyncPayload':
          return UserSyncPayload.fromJson(value);
        case 'UserSyncResponse':
          return UserSyncResponse.fromJson(value);
        case 'ValidationError':
          return ValidationError.fromJson(value);
        default:
          dynamic match;
          if (value is List && (match = _regList.firstMatch(targetType)?.group(1)) != null) {
            return value
              .map<dynamic>((dynamic v) => fromJson(v, match, growable: growable,))
              .toList(growable: growable);
          }
          if (value is Set && (match = _regSet.firstMatch(targetType)?.group(1)) != null) {
            return value
              .map<dynamic>((dynamic v) => fromJson(v, match, growable: growable,))
              .toSet();
          }
          if (value is Map && (match = _regMap.firstMatch(targetType)?.group(1)) != null) {
            return Map<String, dynamic>.fromIterables(
              value.keys.cast<String>(),
              value.values.map<dynamic>((dynamic v) => fromJson(v, match, growable: growable,)),
            );
          }
      }
    } on Exception catch (error, trace) {
      throw ApiException.withInner(HttpStatus.internalServerError, 'Exception during deserialization.', error, trace,);
    }
    throw ApiException(HttpStatus.internalServerError, 'Could not find a suitable class for deserialization',);
  }
}

/// Primarily intended for use in an isolate.
class DeserializationMessage {
  const DeserializationMessage({
    required this.json,
    required this.targetType,
    this.growable = false,
  });

  /// The JSON value to deserialize.
  final String json;

  /// Target type to deserialize to.
  final String targetType;

  /// Whether to make deserialized lists or maps growable.
  final bool growable;
}

/// Primarily intended for use in an isolate.
Future<dynamic> decodeAsync(DeserializationMessage message) async {
  // Remove all spaces. Necessary for regular expressions as well.
  final targetType = message.targetType.replaceAll(' ', '');

  // If the expected target type is String, nothing to do...
  return targetType == 'String'
    ? message.json
    : json.decode(message.json);
}

/// Primarily intended for use in an isolate.
Future<dynamic> deserializeAsync(DeserializationMessage message) async {
  // Remove all spaces. Necessary for regular expressions as well.
  final targetType = message.targetType.replaceAll(' ', '');

  // If the expected target type is String, nothing to do...
  return targetType == 'String'
    ? message.json
    : ApiClient.fromJson(
        json.decode(message.json),
        targetType,
        growable: message.growable,
      );
}

/// Primarily intended for use in an isolate.
Future<String> serializeAsync(Object? value) async => value == null ? '' : json.encode(value);
