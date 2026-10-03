import 'package:projects_api_client/api.dart';
import 'package:test/test.dart';

void main() {
  test('resource profile default applies only to an absent field', () {
    expect(NewProject.fromJson({'name': 'project'})!.resourceProfile,
        NewProjectResourceProfileEnum.medium);
    expect(
        () => NewProject.fromJson(
            {'name': 'project', 'resource_profile': 'unknown'}),
        throwsFormatException);
  });

  test('member role default does not replace an invalid role', () {
    expect(() => AddMember.fromJson({'user_id': 'user', 'role': 'unknown'}),
        throwsFormatException);
  });

  test('content identity exposes only the canonical UUID and reference', () {
    final identity = ContentIdentityResponse.fromJson({
      'project_id': '11111111-1111-4111-8111-111111111111',
      'current_ref': 'abcdefghijklmnopqrst',
    })!;
    expect(identity.toJson().keys.toSet(), {'project_id', 'current_ref'});
    expect(identity.currentRef, 'abcdefghijklmnopqrst');
  });
}
