//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//
// @dart=2.18

// ignore_for_file: unused_element, unused_import
// ignore_for_file: always_put_required_named_parameters_first
// ignore_for_file: constant_identifier_names
// ignore_for_file: lines_longer_than_80_chars

part of openapi.api;

class PolicyResponse {
  /// Returns a new [PolicyResponse] instance.
  PolicyResponse({
    required this.policy,
    required this.projectPolicy,
    required this.revision,
    required this.scope,
    required this.scopeId,
    required this.updatedAt,
  });

  AccessPolicy policy;

  AccessPolicy projectPolicy;

  int revision;

  PolicyResponseScopeEnum scope;

  String scopeId;

  String updatedAt;

  @override
  bool operator ==(Object other) => identical(this, other) || other is PolicyResponse &&
    other.policy == policy &&
    other.projectPolicy == projectPolicy &&
    other.revision == revision &&
    other.scope == scope &&
    other.scopeId == scopeId &&
    other.updatedAt == updatedAt;

  @override
  int get hashCode =>
    // ignore: unnecessary_parenthesis
    (policy.hashCode) +
    (projectPolicy.hashCode) +
    (revision.hashCode) +
    (scope.hashCode) +
    (scopeId.hashCode) +
    (updatedAt.hashCode);

  @override
  String toString() => 'PolicyResponse[policy=$policy, projectPolicy=$projectPolicy, revision=$revision, scope=$scope, scopeId=$scopeId, updatedAt=$updatedAt]';

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
      json[r'policy'] = this.policy;
      json[r'project_policy'] = this.projectPolicy;
      json[r'revision'] = this.revision;
      json[r'scope'] = this.scope;
      json[r'scope_id'] = this.scopeId;
      json[r'updated_at'] = this.updatedAt;
    return json;
  }

  /// Returns a new [PolicyResponse] instance and imports its values from
  /// [value] if it's a [Map], null otherwise.
  // ignore: prefer_constructors_over_static_methods
  static PolicyResponse? fromJson(dynamic value) {
    if (value is Map) {
      final json = value.cast<String, dynamic>();

      const nullableKeys = <String>{};
      for (final key in requiredKeys) {
        if (!json.containsKey(key) || (json[key] == null && !nullableKeys.contains(key))) {
          throw FormatException('Invalid required field: $key');
        }
      }

      return PolicyResponse(
        policy: AccessPolicy.fromJson(json[r'policy'])!,
        projectPolicy: AccessPolicy.fromJson(json[r'project_policy'])!,
        revision: mapValueOfType<int>(json, r'revision')!,
        scope: PolicyResponseScopeEnum.fromJson(json[r'scope'])!,
        scopeId: mapValueOfType<String>(json, r'scope_id')!,
        updatedAt: mapValueOfType<String>(json, r'updated_at')!,
      );
    }
    return null;
  }

  static List<PolicyResponse> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PolicyResponse>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PolicyResponse.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }

  static Map<String, PolicyResponse> mapFromJson(dynamic json) {
    final map = <String, PolicyResponse>{};
    if (json is Map && json.isNotEmpty) {
      json = json.cast<String, dynamic>(); // ignore: parameter_assignments
      for (final entry in json.entries) {
        final value = PolicyResponse.fromJson(entry.value);
        if (value != null) {
          map[entry.key] = value;
        }
      }
    }
    return map;
  }

  // maps a json object with a list of PolicyResponse-objects as value to a dart map
  static Map<String, List<PolicyResponse>> mapListFromJson(dynamic json, {bool growable = false,}) {
    final map = <String, List<PolicyResponse>>{};
    if (json is Map && json.isNotEmpty) {
      // ignore: parameter_assignments
      json = json.cast<String, dynamic>();
      for (final entry in json.entries) {
        map[entry.key] = PolicyResponse.listFromJson(entry.value, growable: growable,);
      }
    }
    return map;
  }

  /// The list of required keys that must be present in a JSON.
  static const requiredKeys = <String>{
    'policy',
    'project_policy',
    'revision',
    'scope',
    'scope_id',
    'updated_at',
  };
}


class PolicyResponseScopeEnum {
  /// Instantiate a new enum with the provided [value].
  const PolicyResponseScopeEnum._(this.value);

  /// The underlying value of this enum member.
  final String value;

  @override
  String toString() => value;

  String toJson() => value;

  static const project = PolicyResponseScopeEnum._(r'project');
  static const slot = PolicyResponseScopeEnum._(r'slot');

  /// List of all possible values in this [enum][PolicyResponseScopeEnum].
  static const values = <PolicyResponseScopeEnum>[
    project,
    slot,
  ];

  static PolicyResponseScopeEnum? fromJson(dynamic value) => PolicyResponseScopeEnumTypeTransformer().decode(value);

  static List<PolicyResponseScopeEnum> listFromJson(dynamic json, {bool growable = false,}) {
    final result = <PolicyResponseScopeEnum>[];
    if (json is List && json.isNotEmpty) {
      for (final row in json) {
        final value = PolicyResponseScopeEnum.fromJson(row);
        if (value != null) {
          result.add(value);
        }
      }
    }
    return result.toList(growable: growable);
  }
}

/// Transformation class that can [encode] an instance of [PolicyResponseScopeEnum] to String,
/// and [decode] dynamic data back to [PolicyResponseScopeEnum].
class PolicyResponseScopeEnumTypeTransformer {
  factory PolicyResponseScopeEnumTypeTransformer() => _instance ??= const PolicyResponseScopeEnumTypeTransformer._();

  const PolicyResponseScopeEnumTypeTransformer._();

  String encode(PolicyResponseScopeEnum data) => data.value;

  /// Decodes a [dynamic value][data] to a PolicyResponseScopeEnum.
  ///
  /// If [allowNull] is true and the [dynamic value][data] cannot be decoded successfully,
  /// then null is returned. However, if [allowNull] is false and the [dynamic value][data]
  /// cannot be decoded successfully, then an [UnimplementedError] is thrown.
  ///
  /// The [allowNull] is very handy when an API changes and a new enum value is added or removed,
  /// and users are still using an old app with the old code.
  PolicyResponseScopeEnum? decode(dynamic data, {bool allowNull = true}) {
    if (data != null) {
      switch (data) {
        case r'project': return PolicyResponseScopeEnum.project;
        case r'slot': return PolicyResponseScopeEnum.slot;
        default:
          if (!allowNull) {
            throw ArgumentError('Unknown enum value to decode: $data');
          }
      }
    }
    return null;
  }

  /// Singleton [PolicyResponseScopeEnumTypeTransformer] instance.
  static PolicyResponseScopeEnumTypeTransformer? _instance;
}


