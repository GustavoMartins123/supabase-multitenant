import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'models/user_profile.dart';
import 'session.dart';
import 'supabase_colors.dart';

class UserProfileLauncher extends StatelessWidget {
  const UserProfileLauncher({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<UserProfile?>(
      valueListenable: Session().profileListenable,
      builder: (context, profile, _) {
        if (profile == null) return const SizedBox.shrink();
        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () => showDialog<void>(
              context: context,
              builder: (_) => const UserProfileDialog(),
            ),
            borderRadius: BorderRadius.circular(24),
            child: Container(
              padding: const EdgeInsets.fromLTRB(6, 6, 14, 6),
              decoration: BoxDecoration(
                color: SupabaseColors.surface200,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: SupabaseColors.border),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x66000000),
                    blurRadius: 16,
                    offset: Offset(0, 6),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _ProfileAvatar(profile: profile, radius: 17),
                  const SizedBox(width: 10),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 180),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          profile.displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: SupabaseColors.textPrimary,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          'Meu perfil',
                          style: const TextStyle(
                            color: SupabaseColors.textMuted,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class UserProfileDialog extends StatefulWidget {
  const UserProfileDialog({super.key});

  @override
  State<UserProfileDialog> createState() => _UserProfileDialogState();
}

class _UserProfileDialogState extends State<UserProfileDialog> {
  final _formKey = GlobalKey<FormState>();
  final Map<String, TextEditingController> _controllers = {};
  bool _saving = false;
  bool _avatarBusy = false;
  String? _error;

  UserProfile get _profile => Session().profile!;

  @override
  void initState() {
    super.initState();
    final profile = _profile;
    final values = <String, String>{
      'display_name': profile.displayName,
      'given_name': profile.givenName,
      'family_name': profile.familyName,
      'middle_name': profile.middleName,
      'nickname': profile.nickname,
      'gender': profile.gender,
      'birthdate': profile.birthdate,
      'website': profile.website,
      'profile': profile.profileUrl,
      'zoneinfo': profile.zoneinfo,
      'locale': profile.locale,
      'phone_number': profile.phoneNumber,
      'phone_extension': profile.phoneExtension,
      'street_address': profile.streetAddress,
      'locality': profile.locality,
      'region': profile.region,
      'postal_code': profile.postalCode,
      'country': profile.country,
    };
    for (final entry in values.entries) {
      _controllers[entry.key] = TextEditingController(text: entry.value);
    }
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  String _value(String key) => _controllers[key]!.text.trim();

  Map<String, String> _payload() => {
        for (final entry in _controllers.entries) entry.key: entry.value.text.trim(),
      };

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final response = await http.patch(
        Uri.parse('/api/user/me'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode(_payload()),
      );
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw StateError(data['error']?.toString() ?? 'Não foi possível salvar o perfil');
      }
      Session().setProfile(UserProfile.fromJson(data));
      if (mounted) Navigator.pop(context);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString().replaceFirst('Bad state: ', ''));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<html.File?> _selectFile() async {
    final input = html.FileUploadInputElement()
      ..accept = 'image/png,image/jpeg,image/webp'
      ..multiple = false;
    input.click();
    await input.onChange.first;
    return input.files?.isNotEmpty == true ? input.files!.first : null;
  }

  Future<Uint8List> _readFile(html.File file) async {
    final reader = html.FileReader();
    final completer = Completer<Uint8List>();
    reader.onLoad.listen((_) {
      final result = reader.result;
      if (result is Uint8List) {
        completer.complete(result);
      } else if (result is ByteBuffer) {
        completer.complete(Uint8List.view(result));
      } else {
        completer.completeError(StateError('Arquivo inválido'));
      }
    });
    reader.onError.listen((_) => completer.completeError(StateError('Falha ao ler a imagem')));
    reader.readAsArrayBuffer(file);
    return completer.future;
  }

  Future<void> _uploadAvatar() async {
    final file = await _selectFile();
    if (file == null) return;
    if (file.size > 2 * 1024 * 1024) {
      setState(() => _error = 'A imagem deve ter no máximo 2 MB');
      return;
    }
    setState(() {
      _avatarBusy = true;
      _error = null;
    });
    try {
      final bytes = await _readFile(file);
      final response = await http.put(
        Uri.parse('/api/user/me/avatar'),
        headers: {'Content-Type': file.type.isEmpty ? 'application/octet-stream' : file.type},
        body: bytes,
      );
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw StateError(data['error']?.toString() ?? 'Não foi possível enviar a foto');
      }
      Session().setProfile(UserProfile.fromJson(data));
      if (mounted) setState(() {});
    } catch (error) {
      if (mounted) setState(() => _error = error.toString().replaceFirst('Bad state: ', ''));
    } finally {
      if (mounted) setState(() => _avatarBusy = false);
    }
  }

  Future<void> _removeAvatar() async {
    setState(() {
      _avatarBusy = true;
      _error = null;
    });
    try {
      final response = await http.delete(Uri.parse('/api/user/me/avatar'));
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw StateError(data['error']?.toString() ?? 'Não foi possível remover a foto');
      }
      Session().setProfile(UserProfile.fromJson(data));
      if (mounted) setState(() {});
    } catch (error) {
      if (mounted) setState(() => _error = error.toString().replaceFirst('Bad state: ', ''));
    } finally {
      if (mounted) setState(() => _avatarBusy = false);
    }
  }

  Widget _field(
    String key,
    String label, {
    String? hint,
    int maxLines = 1,
    bool required = false,
  }) {
    return SizedBox(
      width: 270,
      child: TextFormField(
        controller: _controllers[key],
        maxLines: maxLines,
        style: const TextStyle(color: SupabaseColors.textPrimary, fontSize: 13),
        decoration: InputDecoration(labelText: label, hintText: hint),
        validator: (value) {
          final text = value?.trim() ?? '';
          if (required && text.isEmpty) return 'Campo obrigatório';
          if ((key == 'website' || key == 'profile') &&
              text.isNotEmpty &&
              !text.startsWith('http://') &&
              !text.startsWith('https://')) {
            return 'Use uma URL http ou https';
          }
          if (key == 'birthdate' &&
              text.isNotEmpty &&
              !RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(text)) {
            return 'Use AAAA-MM-DD';
          }
          return null;
        },
      ),
    );
  }

  Widget _section(String title, List<Widget> fields) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title.toUpperCase(),
          style: const TextStyle(
            color: SupabaseColors.textMuted,
            fontSize: 11,
            letterSpacing: 1.1,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 14, children: fields),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final profile = Session().profile!;
    return Dialog(
      backgroundColor: SupabaseColors.bg200,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: SupabaseColors.border),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900, maxHeight: 820),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 20, 16, 16),
              child: Row(
                children: [
                  const Icon(Icons.manage_accounts_outlined, color: SupabaseColors.brand),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'Meu perfil',
                      style: TextStyle(
                        color: SupabaseColors.textPrimary,
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: _saving || _avatarBusy ? null : () => Navigator.pop(context),
                    icon: const Icon(Icons.close, color: SupabaseColors.textSecondary),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: SupabaseColors.border),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          _ProfileAvatar(profile: profile, radius: 42),
                          const SizedBox(width: 18),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  profile.displayName,
                                  style: const TextStyle(
                                    color: SupabaseColors.textPrimary,
                                    fontSize: 18,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '${profile.username} · ${profile.email}',
                                  style: const TextStyle(
                                    color: SupabaseColors.textSecondary,
                                    fontSize: 12,
                                  ),
                                ),
                                const SizedBox(height: 12),
                                Wrap(
                                  spacing: 8,
                                  children: [
                                    OutlinedButton.icon(
                                      onPressed: _avatarBusy ? null : _uploadAvatar,
                                      icon: const Icon(Icons.upload_outlined, size: 17),
                                      label: const Text('Alterar foto'),
                                    ),
                                    if (profile.picture.isNotEmpty)
                                      TextButton.icon(
                                        onPressed: _avatarBusy ? null : _removeAvatar,
                                        icon: const Icon(Icons.delete_outline, size: 17),
                                        label: const Text('Remover'),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 18),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: SupabaseColors.error.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: SupabaseColors.error.withValues(alpha: 0.5)),
                          ),
                          child: Text(_error!, style: const TextStyle(color: SupabaseColors.error)),
                        ),
                      ],
                      const SizedBox(height: 28),
                      _section('Identidade', [
                        _field('display_name', 'Nome de exibição', required: true),
                        _field('given_name', 'Nome'),
                        _field('middle_name', 'Nome do meio'),
                        _field('family_name', 'Sobrenome'),
                        _field('nickname', 'Apelido'),
                        _field('gender', 'Gênero'),
                        _field('birthdate', 'Data de nascimento', hint: 'AAAA-MM-DD'),
                      ]),
                      const SizedBox(height: 28),
                      _section('Contato e presença', [
                        _field('phone_number', 'Telefone'),
                        _field('phone_extension', 'Ramal'),
                        _field('website', 'Website', hint: 'https://...'),
                        _field('profile', 'Página de perfil', hint: 'https://...'),
                      ]),
                      const SizedBox(height: 28),
                      _section('Localização', [
                        _field('street_address', 'Endereço'),
                        _field('locality', 'Cidade'),
                        _field('region', 'Estado ou região'),
                        _field('postal_code', 'CEP'),
                        _field('country', 'País'),
                        _field('zoneinfo', 'Fuso horário', hint: 'America/Sao_Paulo'),
                        _field('locale', 'Idioma', hint: 'pt-BR'),
                      ]),
                      const SizedBox(height: 8),
                    ],
                  ),
                ),
              ),
            ),
            const Divider(height: 1, color: SupabaseColors.border),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: _saving || _avatarBusy ? null : () => Navigator.pop(context),
                    child: const Text('Cancelar'),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton.icon(
                    onPressed: _saving || _avatarBusy ? null : _save,
                    icon: _saving
                        ? const SizedBox(
                            width: 15,
                            height: 15,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.save_outlined, size: 18),
                    label: const Text('Salvar'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileAvatar extends StatelessWidget {
  const _ProfileAvatar({required this.profile, required this.radius});

  final UserProfile profile;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final fallback = Container(
      width: radius * 2,
      height: radius * 2,
      alignment: Alignment.center,
      decoration: const BoxDecoration(
        shape: BoxShape.circle,
        color: SupabaseColors.bg400,
      ),
      child: Text(
        profile.initials,
        style: TextStyle(
          color: SupabaseColors.textPrimary,
          fontSize: radius * 0.62,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
    if (profile.picture.isEmpty) return fallback;
    return ClipOval(
      child: Image.network(
        profile.picture,
        width: radius * 2,
        height: radius * 2,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => fallback,
      ),
    );
  }
}
