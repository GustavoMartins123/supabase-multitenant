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

part 'model/add_member.dart';
part 'model/add_member_response.dart';
part 'model/all_users_member_item.dart';
part 'model/all_users_response.dart';
part 'model/assign_project_tag_response.dart';
part 'model/auth_user_item.dart';
part 'model/auth_users_response.dart';
part 'model/automatic_key_rotation_response.dart';
part 'model/automatic_key_rotation_update.dart';
part 'model/collaboration_hint_item.dart';
part 'model/collaboration_member_item.dart';
part 'model/collaboration_note_item.dart';
part 'model/collaboration_notification_item.dart';
part 'model/collaboration_tag_item.dart';
part 'model/collaboration_thread_item.dart';
part 'model/confirm_api_key_installation.dart';
part 'model/container_info_item.dart';
part 'model/container_logs_response.dart';
part 'model/content_identity_response.dart';
part 'model/create_api_key_slot.dart';
part 'model/create_project_hint_response.dart';
part 'model/create_project_note_response.dart';
part 'model/create_restore_point_response.dart';
part 'model/create_thread_message_response.dart';
part 'model/delete_project_note_response.dart';
part 'model/delete_restore_point_response.dart';
part 'model/duplicate_project.dart';
part 'model/enc_key_response.dart';
part 'model/get_project_collaboration_response.dart';
part 'model/get_project_settings_response.dart';
part 'model/http_validation_error.dart';
part 'model/issued_key_response.dart';
part 'model/job_list_response.dart';
part 'model/job_response.dart';
part 'model/job_retry_response.dart';
part 'model/key_version_response.dart';
part 'model/list_restore_points_response.dart';
part 'model/location_inner.dart';
part 'model/member_item.dart';
part 'model/migration_abort_response.dart';
part 'model/migration_cutover_response.dart';
part 'model/migration_prepare_response.dart';
part 'model/migration_status_response.dart';
part 'model/model_source.dart';
part 'model/new_project.dart';
part 'model/project_ai_function_item.dart';
part 'model/project_config_token_response.dart';
part 'model/project_display_name_update.dart';
part 'model/project_hint_create.dart';
part 'model/project_hint_status_update.dart';
part 'model/project_info_item.dart';
part 'model/project_list_item.dart';
part 'model/project_note_create.dart';
part 'model/project_notification_read.dart';
part 'model/project_queue_in_flight_job.dart';
part 'model/project_queue_status_response.dart';
part 'model/project_rename_history_response.dart';
part 'model/project_rename_request.dart';
part 'model/project_s3_vector_keys_response.dart';
part 'model/project_status_response.dart';
part 'model/project_tag_assign.dart';
part 'model/project_thread_message_create.dart';
part 'model/project_user_telemetry_response.dart';
part 'model/projects_info_response.dart';
part 'model/queued_job_response.dart';
part 'model/recreate_project_services_response.dart';
part 'model/recreate_services.dart';
part 'model/remove_member_response.dart';
part 'model/rename_history_entry.dart';
part 'model/rename_history_event.dart';
part 'model/rename_project_response.dart';
part 'model/restart_project_response.dart';
part 'model/restore_point_create.dart';
part 'model/restore_point_item.dart';
part 'model/restore_points_permissions.dart';
part 'model/restore_restore_point_response.dart';
part 'model/reveal_claim_response.dart';
part 'model/reveal_item.dart';
part 'model/reveal_list_response.dart';
part 'model/rotate_api_key_slot.dart';
part 'model/rotate_project_key_response.dart';
part 'model/slot_activation_response.dart';
part 'model/slot_cancel_response.dart';
part 'model/slot_confirm_response.dart';
part 'model/slot_item.dart';
part 'model/slot_key_item.dart';
part 'model/slot_list_response.dart';
part 'model/slot_policy_update_response.dart';
part 'model/slot_revoke_response.dart';
part 'model/start_project_response.dart';
part 'model/stop_project_response.dart';
part 'model/studio_context_response.dart';
part 'model/telemetry_user_item.dart';
part 'model/transfer_body.dart';
part 'model/transfer_response.dart';
part 'model/unassign_project_tag_response.dart';
part 'model/update_api_key_slot_policy.dart';
part 'model/update_display_name_response.dart';
part 'model/update_notification_read_response.dart';
part 'model/update_project_hint_response.dart';
part 'model/update_project_settings_response.dart';
part 'model/update_settings.dart';
part 'model/user_sync_payload.dart';
part 'model/user_sync_response.dart';
part 'model/validation_error.dart';


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
