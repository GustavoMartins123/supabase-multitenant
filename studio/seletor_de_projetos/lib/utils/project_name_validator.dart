import '../models/project_identity.dart';

class ProjectNameValidator {
  ProjectNameValidator._();

  static final RegExp nameRegExp = RegExp(projectNamePattern);

  static String normalize(String input) {
    return input
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9_]'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
  }

  static bool isValidShape(String name) => nameRegExp.hasMatch(name);

}
