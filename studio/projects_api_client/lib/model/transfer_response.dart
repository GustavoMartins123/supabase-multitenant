//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class TransferResponse {
  /// Returns a new [TransferResponse] instance.
  TransferResponse({
    this.detail,
    this.newOwnerId,
    this.project,
    required this.status,
  });

  String? detail;

  String? newOwnerId;

  String? project;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is TransferResponse &&
    other.detail == detail &&
    other.newOwnerId == newOwnerId &&
    other.project == project &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (detail == null ? 0 : detail!.hashCode) +
    (newOwnerId == null ? 0 : newOwnerId!.hashCode) +
    (project == null ? 0 : project!.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'TransferResponse[detail=$detail, newOwnerId=$newOwnerId, project=$project, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (this.detail != null) {
      json[r'detail'] = this.detail;
    } else {
      json[r'detail'] = null;
    }
    if (this.newOwnerId != null) {
      json[r'new_owner_id'] = this.newOwnerId;
    } else {
      json[r'new_owner_id'] = null;
    }
    if (this.project != null) {
      json[r'project'] = this.project;
    } else {
      json[r'project'] = null;
    }
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [TransferResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static TransferResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "TransferResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "TransferResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return TransferResponse(
        detail: mapValueOfType<String>(json, r'detail'),
        newOwnerId: mapValueOfType<String>(json, r'new_owner_id'),
        project: mapValueOfType<String>(json, r'project'),
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<TransferResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <TransferResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = TransferResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, TransferResponse> mapFromJson(dynamic json) {
    final map = <String, TransferResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = TransferResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of TransferResponse-objects as value to a dart map
  static Map<String, List<TransferResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<TransferResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = TransferResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'status',
  };
}

