import 'package:flutter_test/flutter_test.dart';
import 'package:projects_api_client/api.dart';

void main() {
  Map<String, dynamic> configuration() => {
    'supabase_url': 'https://api.example.test/abcdefghijklmnopqrst',
    'publishable_key': 'sb_publishable_test',
    'key_id': '11111111-1111-4111-8111-111111111111',
    'expires_at': null,
  };

  test('generated discovery contract accepts explicit null expiration', () {
    final json = configuration();
    final parsed = ClientConfigurationResponse.fromJson(json)!;
    expect(parsed.expiresAt, isNull);
    expect(parsed.toJson(), json);
  });

  test('generated discovery contract rejects missing required fields', () {
    for (final field in configuration().keys) {
      expect(
        () => ClientConfigurationResponse.fromJson(configuration()..remove(field)),
        throwsFormatException,
      );
    }
  });
}
