import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

enum ApiFailureKind {
  unauthorized,
  forbidden,
  notFound,
  conflict,
  validation,
  server,
  timeout,
  cancelled,
  transport,
  invalidResponse,
  unexpectedStatus,
}

final class ApiException implements Exception {
  const ApiException(
    this.kind,
    this.message, {
    this.statusCode,
    this.uri,
  });

  final ApiFailureKind kind;
  final String message;
  final int? statusCode;
  final Uri? uri;

  factory ApiException.fromResponse(http.Response response) {
    final statusCode = response.statusCode;
    final kind = switch (statusCode) {
      401 => ApiFailureKind.unauthorized,
      403 => ApiFailureKind.forbidden,
      404 => ApiFailureKind.notFound,
      409 => ApiFailureKind.conflict,
      400 || 422 => ApiFailureKind.validation,
      >= 500 => ApiFailureKind.server,
      _ => ApiFailureKind.unexpectedStatus,
    };
    return ApiException(
      kind,
      _responseMessage(response),
      statusCode: statusCode,
      uri: response.request?.url,
    );
  }

  static String _responseMessage(http.Response response) {
    final body = response.body.trim();
    if (body.isEmpty) return 'HTTP ${response.statusCode}';

    if (_looksLikeHtml(response)) {
      return 'O servidor devolveu HTML para uma chamada de API '
          '(HTTP ${response.statusCode})';
    }

    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        final errors = decoded['errors'];
        if (errors is List && errors.isNotEmpty) {
          return errors.map((error) => error.toString()).join('\n');
        }
        for (final key in const ['detail', 'message', 'error']) {
          final value = decoded[key];
          if (value != null && value.toString().trim().isNotEmpty) {
            return value.toString();
          }
        }
      }
    } on FormatException {
      // A body textual ainda e o diagnostico canonico da resposta HTTP.
    }
    return body.length <= 500 ? body : '${body.substring(0, 500)}…';
  }

  @override
  String toString() => message;
}

Object? decodeJsonResponse(
  http.Response response, {
  required String context,
}) {
  final body = response.body.trim();
  if (body.isEmpty) {
    throw ApiException(
      ApiFailureKind.invalidResponse,
      '$context: resposta vazia',
      statusCode: response.statusCode,
      uri: response.request?.url,
    );
  }
  if (_looksLikeHtml(response)) {
    throw ApiException(
      ApiFailureKind.invalidResponse,
      '$context: o servidor devolveu HTML em vez de JSON',
      statusCode: response.statusCode,
      uri: response.request?.url,
    );
  }

  try {
    return jsonDecode(body);
  } on FormatException {
    throw ApiException(
      ApiFailureKind.invalidResponse,
      '$context: JSON invalido',
      statusCode: response.statusCode,
      uri: response.request?.url,
    );
  }
}

Map<String, dynamic>? tryDecodeJsonObjectBody(String body) {
  if (body.trim().isEmpty) return null;
  try {
    final decoded = jsonDecode(body);
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  } on FormatException {
    return null;
  }
}

Map<String, dynamic> decodeJsonObject(
  http.Response response, {
  required String context,
}) {
  final decoded = decodeJsonResponse(response, context: context);
  if (decoded is! Map) {
    throw ApiException(
      ApiFailureKind.invalidResponse,
      '$context: era esperado um objeto JSON',
      statusCode: response.statusCode,
      uri: response.request?.url,
    );
  }
  return Map<String, dynamic>.from(decoded);
}

List<dynamic> decodeJsonList(
  http.Response response, {
  required String context,
}) {
  final decoded = decodeJsonResponse(response, context: context);
  if (decoded is! List) {
    throw ApiException(
      ApiFailureKind.invalidResponse,
      '$context: era esperada uma lista JSON',
      statusCode: response.statusCode,
      uri: response.request?.url,
    );
  }
  return List<dynamic>.from(decoded);
}

bool _looksLikeHtml(http.Response response) {
  final contentType = response.headers['content-type']?.toLowerCase() ?? '';
  if (contentType.contains('text/html') ||
      contentType.contains('application/xhtml+xml')) {
    return true;
  }
  final body = response.body.trimLeft().toLowerCase();
  return body.startsWith('<!doctype html') ||
      body.startsWith('<html') ||
      body.startsWith('<head') ||
      body.startsWith('<body');
}

final class RequestCancellation {
  final Completer<void> _completer = Completer<void>();

  bool get isCancelled => _completer.isCompleted;
  Future<void> get whenCancelled => _completer.future;

  void cancel() {
    if (!_completer.isCompleted) _completer.complete();
  }
}

final class ApiClient {
  ApiClient({
    http.Client? client,
    this.timeout = const Duration(seconds: 15),
  }) : _client = client ?? http.Client();

  final http.Client _client;
  final Duration timeout;

  static void Function()? _unauthorizedHandler;
  static bool _unauthorizedHandlerCalled = false;

  static set unauthorizedHandler(void Function()? handler) {
    _unauthorizedHandler = handler;
    _unauthorizedHandlerCalled = false;
  }

  Future<http.Response> get(
    Uri uri, {
    Map<String, String>? headers,
    RequestCancellation? cancellation,
  }) =>
      send('GET', uri, headers: headers, cancellation: cancellation);

  Future<http.Response> post(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    RequestCancellation? cancellation,
  }) =>
      send(
        'POST',
        uri,
        headers: headers,
        body: body,
        cancellation: cancellation,
      );

  Future<http.Response> put(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    RequestCancellation? cancellation,
  }) =>
      send(
        'PUT',
        uri,
        headers: headers,
        body: body,
        cancellation: cancellation,
      );

  Future<http.Response> patch(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    RequestCancellation? cancellation,
  }) =>
      send(
        'PATCH',
        uri,
        headers: headers,
        body: body,
        cancellation: cancellation,
      );

  Future<http.Response> delete(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    RequestCancellation? cancellation,
  }) =>
      send(
        'DELETE',
        uri,
        headers: headers,
        body: body,
        cancellation: cancellation,
      );

  Future<http.Response> send(
    String method,
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
    RequestCancellation? cancellation,
  }) async {
    if (cancellation?.isCancelled == true) {
      throw ApiException(
        ApiFailureKind.cancelled,
        'Requisicao cancelada',
        uri: uri,
      );
    }

    final abort = Completer<void>();
    final request = http.AbortableRequest(
      method,
      uri,
      abortTrigger: abort.future,
    );
    if (headers != null) request.headers.addAll(headers);
    if (_isApiUri(uri)) {
      request.headers.putIfAbsent('Accept', () => 'application/json');
    }
    if (body case final String text) {
      request.body = text;
    } else if (body case final List<int> bytes) {
      request.bodyBytes = bytes;
    } else if (body != null) {
      throw ArgumentError.value(body, 'body', 'Use String ou List<int>');
    }

    var completed = false;
    var timedOut = false;
    var cancelled = false;

    void abortRequest() {
      if (!abort.isCompleted) abort.complete();
    }

    final timer = Timer(timeout, () {
      if (completed) return;
      timedOut = true;
      abortRequest();
    });
    cancellation?.whenCancelled.then((_) {
      if (completed) return;
      cancelled = true;
      abortRequest();
    });

    Future<http.Response> aborted() async {
      await abort.future;
      if (timedOut) {
        throw ApiException(
          ApiFailureKind.timeout,
          'Tempo limite de ${timeout.inSeconds}s excedido',
          uri: uri,
        );
      }
      if (cancelled) {
        throw ApiException(
          ApiFailureKind.cancelled,
          'Requisicao cancelada',
          uri: uri,
        );
      }
      throw ApiException(
        ApiFailureKind.transport,
        'Requisicao interrompida',
        uri: uri,
      );
    }

    try {
      final response = await Future.any<http.Response>([
        _sendAndValidate(request, uri),
        aborted(),
      ]);
      return response;
    } on ApiException {
      rethrow;
    } on http.RequestAbortedException {
      if (timedOut) {
        throw ApiException(
          ApiFailureKind.timeout,
          'Tempo limite de ${timeout.inSeconds}s excedido',
          uri: uri,
        );
      }
      throw ApiException(
        ApiFailureKind.cancelled,
        'Requisicao cancelada',
        uri: uri,
      );
    } on http.ClientException catch (error) {
      throw ApiException(
        ApiFailureKind.transport,
        error.message,
        uri: error.uri ?? uri,
      );
    } finally {
      completed = true;
      timer.cancel();
    }
  }

  Future<http.Response> _sendAndValidate(
    http.BaseRequest request,
    Uri requestedUri,
  ) async {
    final streamed = await _client.send(request);
    final effectiveUri = switch (streamed) {
      http.BaseResponseWithUrl(:final url) => url,
      _ => null,
    };
    final response = await http.Response.fromStream(streamed);

    if (!_isApiUri(requestedUri)) return response;

    final location = response.headers['location'];
    final locationUri =
        location == null ? null : requestedUri.resolve(location);
    final authenticationRedirect =
        _isAuthenticationUri(effectiveUri) || _isAuthenticationUri(locationUri);
    if (response.statusCode == 401 || authenticationRedirect) {
      _notifyUnauthorized();
      throw ApiException(
        ApiFailureKind.unauthorized,
        'Sua sessao expirou. Redirecionando para o login.',
        statusCode: response.statusCode,
        uri: requestedUri,
      );
    }

    if (response.statusCode >= 200 &&
        response.statusCode < 300 &&
        _looksLikeHtml(response)) {
      throw ApiException(
        ApiFailureKind.invalidResponse,
        'O servidor devolveu HTML para ${requestedUri.path}; '
        'verifique o roteamento da API.',
        statusCode: response.statusCode,
        uri: requestedUri,
      );
    }
    return response;
  }

  static bool _isApiUri(Uri uri) =>
      uri.path == '/api' ||
      uri.path.startsWith('/api/') ||
      uri.path.startsWith('/_internal_api/');

  static bool _isAuthenticationUri(Uri? uri) {
    if (uri == null) return false;
    return uri.path == '/auth' ||
        uri.path.startsWith('/auth/') ||
        uri.path == '/login' ||
        uri.path == '/logout';
  }

  static void _notifyUnauthorized() {
    if (_unauthorizedHandlerCalled) return;
    _unauthorizedHandlerCalled = true;
    _unauthorizedHandler?.call();
  }

  void close() => _client.close();
}
