// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

Future<String?> pickMailerHtml() async {
  final picker = html.FileUploadInputElement()..accept = '.html,.htm,text/html';
  final selection = Completer<html.File?>();
  final change = picker.onChange.listen((_) {
    if (!selection.isCompleted) selection.complete(picker.files?.firstOrNull);
  });
  final cancel = picker.on['cancel'].listen((_) {
    if (!selection.isCompleted) selection.complete(null);
  });
  picker.click();
  try {
    final file = await selection.future;
    if (file == null) return null;
    if (file.size == 0 || file.size > 1024 * 1024) {
      throw const FormatException('O HTML deve conter entre 1 byte e 1 MB.');
    }
    final reader = html.FileReader()..readAsArrayBuffer(file);
    await reader.onLoadEnd.first;
    if (reader.error != null) {
      throw const FormatException('Não foi possível ler o arquivo.');
    }
    return utf8.decode(reader.result as Uint8List, allowMalformed: false);
  } finally {
    await change.cancel();
    await cancel.cancel();
    picker.remove();
  }
}
