//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class ContainerLogsResponse {
  /// Returns a new [ContainerLogsResponse] instance.
  ContainerLogsResponse({
    required this.container,
    required this.logs,
    required this.status,
  });

  String container;

  String logs;

  String status;

  @override
  bool operator ==(Object other) => identical(this, other) || other is ContainerLogsResponse &&
    other.container == container &&
    other.logs == logs &&
    other.status == status;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (container.hashCode) +
    (logs.hashCode) +
    (status.hashCode);

  @override
  String toString() => 'ContainerLogsResponse[container=$container, logs=$logs, status=$status]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'container'] = this.container;
      json[r'logs'] = this.logs;
      json[r'status'] = this.status;
    return json;
  }

  /// Returns a new [ContainerLogsResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static ContainerLogsResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      // Ensure that the map contains the required keys.
      // Note 1: the values aren't checked for validity beyond being non-null.
      // Note 2: this code is stripped in release mode!
      assert(() {
        requiredKeys.forEach((key) {
          assert(json.containsKey(key), 'Required key "ContainerLogsResponse[$key]" is missing from JSON.');
          assert(json[key] != null, 'Required key "ContainerLogsResponse[$key]" has a null value in JSON.');
        });
        return true;
      }());

      return ContainerLogsResponse(
        container: mapValueOfType<String>(json, r'container')!,
        logs: mapValueOfType<String>(json, r'logs')!,
        status: mapValueOfType<String>(json, r'status')!,
      );
    }
    return null;
  }

  static List<ContainerLogsResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <ContainerLogsResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = ContainerLogsResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, ContainerLogsResponse> mapFromJson(dynamic json) {
    final map = <String, ContainerLogsResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = ContainerLogsResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of ContainerLogsResponse-objects as value to a dart map
  static Map<String, List<ContainerLogsResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<ContainerLogsResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = ContainerLogsResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'container',
    'logs',
    'status',
  };
}

