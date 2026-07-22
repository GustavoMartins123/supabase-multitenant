import 'package:web/web.dart' as web;

String loginUrl() => '${web.window.location.origin}/login';

String logoutUrl() => '${web.window.location.origin}/logout';

void redirectToLogin() => web.window.location.replace(loginUrl());

void redirectToLogout() => web.window.location.replace(logoutUrl());
