String clientConfigurationUrl(String publicBaseUrl, String applicationRef) {
  final base = Uri.parse(publicBaseUrl);
  if (!['http', 'https'].contains(base.scheme) || base.host.isEmpty ||
      base.userInfo.isNotEmpty || base.hasQuery || base.hasFragment ||
      !['', '/'].contains(base.path) || applicationRef.length != 20 ||
      !RegExp(r'^[a-z]{20}$').hasMatch(applicationRef)) {
    throw const FormatException('Origem publica ou referencia do aplicativo invalida');
  }
  return base.resolve('/config/$applicationRef').toString();
}
