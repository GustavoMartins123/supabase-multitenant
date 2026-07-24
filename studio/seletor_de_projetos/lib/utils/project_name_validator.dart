/// Fonte unica do formato e dos nomes reservados de slug de projeto,
/// espelhando servidor/api-internal/app/host_agent_protocol.py.
class ProjectNameValidator {
  ProjectNameValidator._();

  static final RegExp nameRegExp = RegExp(r'^[a-z_][a-z0-9_]{2,39}$');

  static const Set<String> reservedWords = <String>{
    'default',
    'select',
    'from',
    'where',
    'insert',
    'update',
    'delete',
    'table',
    'create',
    'drop',
    'join',
    'group',
    'order',
    'limit',
    'into',
    'index',
    'view',
    'trigger',
    'procedure',
    'function',
    'database',
    'schema',
    'primary',
    'foreign',
    'key',
    'constraint',
    'unique',
    'null',
    'not',
    'and',
    'or',
    'in',
    'like',
    'between',
    'exists',
    'having',
    'union',
    'inner',
    'left',
    'right',
    'outer',
    'cross',
    'on',
    'as',
    'case',
    'when',
    'then',
    'else',
    'end',
    'if',
    'while',
    'for',
    'begin',
    'commit',
    'rollback',
    'admin',
    'phpmyadmin',
    'xmlrpc',
    'actuator',
  };

  static String normalize(String input) {
    return input
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9_]'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
  }

  static bool isValidShape(String name) => nameRegExp.hasMatch(name);

  static bool isReserved(String name) => reservedWords.contains(name);
}
