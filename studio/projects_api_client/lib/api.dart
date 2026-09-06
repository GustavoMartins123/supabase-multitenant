//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

library openapi.api;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:http/http.dart';
import 'package:intl/intl.dart';
import 'package:meta/meta.dart';

part 'api_client.dart';
part 'api_helper.dart';
part 'api_exception.dart';
part 'auth/authentication.dart';
part 'auth/api_key_auth.dart';
part 'auth/oauth.dart';
part 'auth/http_basic_auth.dart';
part 'auth/http_bearer_auth.dart';

part 'api/collaboration_api.dart';
part 'api/internal_api.dart';
part 'api/jobs_api.dart';
part 'api/lifecycle_api.dart';
part 'api/lifecycle_ops_api.dart';
part 'api/opaque_api_keys_api.dart';
part 'api/platform_auth_api.dart';
part 'api/project_insights_api.dart';
part 'api/project_keys_api.dart';
part 'api/project_members_api.dart';
part 'api/project_rename_api.dart';
part 'api/projects_api.dart';
part 'api/restore_points_api.dart';

part 'model/activate_at.dart';
part 'model/add_member.dart';
part 'model/allowed_services.dart';
part 'model/automatic_key_rotation_update.dart';
part 'model/automatic_rotation_enabled.dart';
part 'model/confirm_api_key_installation.dart';
part 'model/create_api_key_slot.dart';
part 'model/duplicate_project.dart';
part 'model/http_validation_error.dart';
part 'model/model_source.dart';
part 'model/new_project.dart';
part 'model/project_display_name_update.dart';
part 'model/project_hint_create.dart';
part 'model/project_hint_status_update.dart';
part 'model/project_note_create.dart';
part 'model/project_notification_read.dart';
part 'model/project_rename_request.dart';
part 'model/project_tag_assign.dart';
part 'model/project_thread_message_create.dart';
part 'model/recreate_services.dart';
part 'model/restore_point_create.dart';
part 'model/rotate_api_key_slot.dart';
part 'model/rotation_interval_days.dart';
part 'model/rotation_interval_days1.dart';
part 'model/transfer_body.dart';
part 'model/update_api_key_slot_policy.dart';
part 'model/update_settings.dart';
part 'model/user_sync_payload.dart';
part 'model/validation_error.dart';
part 'model/validation_error_loc_inner.dart';


/// An [ApiClient] instance that uses the default values obtained from
/// the OpenAPI specification file.
var defaultApiClient = ApiClient();

const _delimiters = {'csv': ',', 'ssv': ' ', 'tsv': '\t', 'pipes': '|'};
const _dateEpochMarker = 'epoch';
const _deepEquality = DeepCollectionEquality();
final _dateFormatter = DateFormat('yyyy-MM-dd');
final _regList = RegExp(r'^List<(.*)>$');
final _regSet = RegExp(r'^Set<(.*)>$');
final _regMap = RegExp(r'^Map<String,(.*)>$');

bool _isEpochMarker(String? pattern) => pattern == _dateEpochMarker || pattern == '/$_dateEpochMarker/';
