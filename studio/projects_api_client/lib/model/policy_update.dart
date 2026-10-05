//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class PolicyUpdate {
  /// Returns a new [PolicyUpdate] instance.
  PolicyUpdate({
    required this.policy,
    required this.revision,
  });

  AccessPolicy policy;

  /// Minimum value: 1
  /// Maximum value: 9007199254740991
  int revision;

  @override
  bool operator ==(Object other) => identical(this, other) || other is PolicyUpdate &&
    other.policy == policy &&
    other.revision == revision;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (policy.hashCode) +
    (revision.hashCode);

  @override
  String toString() => 'PolicyUpdate[policy=$policy, revision=$revision]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'policy'] = this.policy;
      json[r'revision'] = this.revision;
    return json;
  }

  /// Returns a new [PolicyUpdate] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static PolicyUpdate? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return PolicyUpdate(
        policy: AccessPolicy.fromJson(json[r'policy'])!,
        revision: mapValueOfType<int>(json, r'revision')!,
      );
    }
    return null;
  }

  static List<PolicyUpdate> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PolicyUpdate>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PolicyUpdate.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, PolicyUpdate> mapFromJson(dynamic json) {
    final map = <String, PolicyUpdate>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = PolicyUpdate.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of PolicyUpdate-objects as value to a dart map
  static Map<String, List<PolicyUpdate>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<PolicyUpdate>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = PolicyUpdate.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'policy',
    'revision',
  };
}

