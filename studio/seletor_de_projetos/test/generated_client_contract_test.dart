import 'package:flutter_test/flutter_test.dart';
import 'package:projects_api_client/api.dart';

void main() {
  test('null-only folder parent is explicit and rejects non-null values', () {
    expect(FolderBody.fromJson({'name': 'SQL', 'parentId': null})!.parentId,
        isNull);
    expect(FolderBody.fromJson({'name': 'SQL'})!.parentId, isNull);
    expect(
      () => FolderBody.fromJson({'name': 'SQL', 'parentId': 'not-supported'}),
      throwsFormatException,
    );
  });
}
