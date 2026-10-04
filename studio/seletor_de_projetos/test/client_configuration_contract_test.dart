import 'package:flutter_test/flutter_test.dart';
import 'package:seletor_de_projetos/models/client_configuration.dart';

void main() {
  test('discovery uses public data-plane origin, never the Studio origin', () {
    expect(clientConfigurationUrl('https://api.example.test:8443', 'abcdefghijklmnopqrst'),
        'https://api.example.test:8443/config/abcdefghijklmnopqrst');
  });

  test('discovery rejects invalid origin or application reference', () {
    for (final base in ['', 'api.example.test', 'https://api.example.test/project',
      'https://user@api.example.test', 'https://api.example.test?query=1', 'https://api.example.test#fragment']) {
      expect(() => clientConfigurationUrl(base, 'abcdefghijklmnopqrst'), throwsFormatException);
    }
    for (final ref in ['', 'a' * 19, 'a' * 20 + '\n', 'A' * 20]) {
      expect(() => clientConfigurationUrl('https://api.example.test', ref), throwsFormatException);
    }
  });
}
