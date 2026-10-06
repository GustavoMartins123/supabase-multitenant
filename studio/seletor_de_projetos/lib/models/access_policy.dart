class AccessPolicySnapshot {
  AccessPolicySnapshot.fromJson(Map<String, dynamic> json)
      : scope = json['scope'] as String,
        scopeId = json['scope_id'] as String,
        revision = json['revision'] as int,
        policy = Map<String, dynamic>.from(json['policy'] as Map),
        projectPolicy =
            Map<String, dynamic>.from(json['project_policy'] as Map) {
    if (!{'project', 'slot'}.contains(scope) ||
        revision < 1 ||
        scopeId.isEmpty) {
      throw const FormatException('Identidade de política inválida');
    }
    validateAccessPolicy(policy);
    validateAccessPolicy(projectPolicy);
    if (projectPolicy['geo_mode'] == 'inherit' ||
        (scope == 'slot' && policy['geo_mode'] == 'unrestricted') ||
        (scope == 'project' && policy['geo_mode'] == 'inherit')) {
      throw const FormatException('Escopo de política inválido');
    }
  }

  final String scope;
  final String scopeId;
  final int revision;
  final Map<String, dynamic> policy;
  final Map<String, dynamic> projectPolicy;
}

void validateAccessPolicy(Map<String, dynamic> policy) {
  const keys = {
    'geo_mode',
    'allowed_countries',
    'allowed_networks',
    'rate_limit',
    'request_quota'
  };
  if (policy.keys.toSet().difference(keys).isNotEmpty ||
      keys.difference(policy.keys.toSet()).isNotEmpty ||
      !{'inherit', 'restrict', 'unrestricted'}.contains(policy['geo_mode'])) {
    throw const FormatException('Contrato de política inválido');
  }
  final countries = policy['allowed_countries'];
  final networks = policy['allowed_networks'];
  if (networks is! List ||
      networks.any((value) => value is! String) ||
      (policy['geo_mode'] == 'restrict' &&
          (countries is! List ||
              countries.any((value) =>
                  value is! String ||
                  !RegExp(r'^[A-Z]{2}$').hasMatch(value)))) ||
      (policy['geo_mode'] != 'restrict' &&
          (countries != null || networks.isNotEmpty))) {
    throw const FormatException('Geografia inválida');
  }
  final rate = policy['rate_limit'];
  final quota = policy['request_quota'];
  if (rate != null &&
      (rate is! Map ||
          rate.length != 2 ||
          rate['requests_per_second'] is! int ||
          rate['burst'] is! int ||
          rate['requests_per_second'] < 1 ||
          rate['requests_per_second'] > 100000 ||
          rate['burst'] < 1 ||
          rate['burst'] > 1000000)) {
    throw const FormatException('Limite de taxa inválido');
  }
  if (quota != null &&
      (quota is! Map ||
          quota.length != 2 ||
          !{'day', 'month'}.contains(quota['period']) ||
          quota['limit'] is! int ||
          quota['limit'] < 1 ||
          quota['limit'] > 1000000000000)) {
    throw const FormatException('Quota inválida');
  }
}

class AccessCountry {
  AccessCountry.fromJson(Map<String, dynamic> json)
      : code = json['code'] as String,
        name = json['name'] as String,
        nameEn = json['name_en'] as String {
    if (!RegExp(r'^[A-Z]{2}$').hasMatch(code) ||
        name.isEmpty ||
        nameEn.isEmpty) {
      throw const FormatException('Catálogo de países inválido');
    }
  }
  final String code;
  final String name;
  final String nameEn;
}
