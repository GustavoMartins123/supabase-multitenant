import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../models/access_policy.dart';
import '../../services/access_policy_service.dart';
import '../../services/step_up_authentication_service.dart';
import '../../supabase_colors.dart';
import '../step_up_authentication_dialog.dart';

Future<void> showAccessPolicyDialog(BuildContext context,
        {required String projectRef, String? slotId, bool secret = false}) =>
    showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => AccessPolicyDialog(
            projectRef: projectRef, slotId: slotId, secret: secret));

class AccessPolicyDialog extends ConsumerStatefulWidget {
  const AccessPolicyDialog(
      {super.key,
      required this.projectRef,
      this.slotId,
      this.secret = false,
      this.service});
  final String projectRef;
  final String? slotId;
  final bool secret;
  final AccessPolicyService? service;
  @override
  ConsumerState<AccessPolicyDialog> createState() => _AccessPolicyDialogState();
}

class _AccessPolicyDialogState extends ConsumerState<AccessPolicyDialog> {
  late final AccessPolicyService service;
  AccessPolicySnapshot? snapshot;
  List<AccessCountry> catalog = [];
  Set<String> selected = {};
  String mode = '', search = '', period = 'day';
  String? error;
  bool busy = false, dirty = false, rate = false, quota = false;
  List<Map<String, dynamic>>? usage;
  final networks = TextEditingController();
  final rps = TextEditingController();
  final burst = TextEditingController();
  final ceiling = TextEditingController();

  @override
  void initState() {
    super.initState();
    service = widget.service ?? AccessPolicyService();
    load();
  }

  @override
  void dispose() {
    if (widget.service == null) service.close();
    networks.dispose();
    rps.dispose();
    burst.dispose();
    ceiling.dispose();
    super.dispose();
  }

  Future<void> load() async {
    setState(() {
      busy = true;
      error = null;
      snapshot = null;
      usage = null;
    });
    try {
      final value = await service.get(widget.projectRef, widget.slotId);
      final countries = await service.countries();
      if (!mounted) return;
      final policy = value.policy;
      setState(() {
        snapshot = value;
        catalog = countries;
        mode = policy['geo_mode'] as String;
        selected = policy['allowed_countries'] == null
            ? {}
            : Set<String>.from(policy['allowed_countries'] as List);
        networks.text = (policy['allowed_networks'] as List).join(', ');
        rate = policy['rate_limit'] != null;
        quota = policy['request_quota'] != null;
        rps.text = rate
            ? policy['rate_limit']['requests_per_second'].toString()
            : '10';
        burst.text = rate ? policy['rate_limit']['burst'].toString() : '20';
        ceiling.text =
            quota ? policy['request_quota']['limit'].toString() : '10000';
        period = quota ? policy['request_quota']['period'] as String : 'day';
        dirty = false;
        usage = null;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          error = e.toString();
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          busy = false;
        });
      }
    }
  }

  void change(VoidCallback action) => setState(() {
        action();
        dirty = true;
      });
  int positive(TextEditingController controller, int max) {
    final value = int.tryParse(controller.text);
    if (value == null || value < 1 || value > max) {
      throw FormatException('Informe um inteiro entre 1 e $max.');
    }
    return value;
  }

  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final policy = <String, dynamic>{
        'geo_mode': mode,
        'allowed_countries': mode == 'restrict' ? selected.toList() : null,
        'allowed_networks': mode == 'restrict'
            ? networks.text
                .split(',')
                .map((v) => v.trim())
                .where((v) => v.isNotEmpty)
                .toList()
            : <String>[],
        'rate_limit': rate
            ? {
                'requests_per_second': positive(rps, 100000),
                'burst': positive(burst, 1000000)
              }
            : null,
        'request_quota': quota
            ? {'period': period, 'limit': positive(ceiling, 1000000000000)}
            : null
      };
      String? stepUp;
      if (widget.slotId == null || widget.secret) {
        final auth = ref.read(stepUpAuthenticationServiceProvider);
        stepUp = await showStepUpAuthenticationDialog(context,
            title: 'Autorizar política de acesso',
            description:
                'Confirme sua senha para aplicar a revisão ${snapshot!.revision}.',
            authenticate: (password) => auth.requestToken(
                password: password,
                action: StepUpAction.updateAccessPolicy,
                projectRef: widget.projectRef,
                resourceId: '${snapshot!.scopeId}:${snapshot!.revision}'));
        if (stepUp == null) return;
      }
      final value = await service.save(
          widget.projectRef, widget.slotId, snapshot!.revision, policy, stepUp);
      if (mounted) {
        setState(() {
          snapshot = value;
          dirty = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = e.toString();
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          busy = false;
        });
      }
    }
  }

  Future<void> fetchUsage() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final values = await service.usage(widget.projectRef);
      if (mounted) {
        setState(() {
          usage = values
              .where((row) =>
                  row['scope_id'] == snapshot!.scopeId &&
                  row['scope_type'] == snapshot!.scope)
              .toList();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = e.toString();
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          busy = false;
        });
      }
    }
  }

  Future<bool> discard() async {
    if (!dirty) return true;
    return await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
                    title: const Text('Descartar alterações não salvas?'),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(context, false),
                          child: const Text('Continuar editando')),
                      TextButton(
                          onPressed: () => Navigator.pop(context, true),
                          child: const Text('Descartar'))
                    ])) ==
        true;
  }

  Widget number(String label, TextEditingController controller) => Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
          controller: controller,
          enabled: !busy,
          keyboardType: TextInputType.number,
          decoration: InputDecoration(labelText: label),
          onChanged: (_) => change(() {})));

  String parentSummary() {
    final parent = snapshot!.projectPolicy;
    if (parent['geo_mode'] == 'unrestricted') {
      return 'O projeto não restringe países. O slot pode restringir seu próprio acesso.';
    }
    final countries = (parent['allowed_countries'] as List).length;
    final networks = (parent['allowed_networks'] as List).length;
    return 'Projeto: $countries países e $networks redes permitidos. A regra do slot também precisa permitir a origem; ela não amplia a permissão do projeto.';
  }

  @override
  Widget build(BuildContext context) {
    final query = search.toLowerCase();
    final visible = catalog
        .where((c) =>
            c.code.toLowerCase().contains(query) ||
            c.name.toLowerCase().contains(query) ||
            c.nameEn.toLowerCase().contains(query))
        .toList();
    return PopScope(
        canPop: !busy && !dirty,
        child: AlertDialog(
          backgroundColor: SupabaseColors.bg200,
          title: Text(widget.slotId == null
              ? 'Acesso e limites do projeto'
              : 'Acesso e limites do aplicativo'),
          content: SizedBox(
              width: 620,
              child: SingleChildScrollView(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    if (busy) const LinearProgressIndicator(),
                    if (error != null)
                      Text(error!,
                          style: const TextStyle(color: SupabaseColors.error)),
                    if (snapshot != null) ...[
                      if (widget.slotId != null) Text(parentSummary()),
                      DropdownButtonFormField<String>(
                          key: ValueKey('geo-${snapshot!.revision}-$mode'),
                          initialValue: mode,
                          decoration: const InputDecoration(
                              labelText: 'Acesso geográfico'),
                          items: [
                            DropdownMenuItem(
                                value: widget.slotId == null
                                    ? 'unrestricted'
                                    : 'inherit',
                                child: Text(widget.slotId == null
                                    ? 'Sem restrição de país'
                                    : 'Herdar política do projeto')),
                            const DropdownMenuItem(
                                value: 'restrict',
                                child: Text('Restringir países e redes'))
                          ],
                          onChanged: busy
                              ? null
                              : (v) => change(() {
                                    mode = v!;
                                  })),
                      if (mode == 'restrict') ...[
                        TextField(
                            enabled: !busy,
                            decoration: const InputDecoration(
                                labelText: 'Buscar país ou código'),
                            onChanged: (v) => setState(() {
                                  search = v;
                                })),
                        Wrap(children: [
                          TextButton(
                              onPressed: busy
                                  ? null
                                  : () => change(() {
                                        selected =
                                            catalog.map((c) => c.code).toSet();
                                      }),
                              child: const Text('Selecionar todos')),
                          TextButton(
                              onPressed: busy
                                  ? null
                                  : () => change(() {
                                        selected.clear();
                                      }),
                              child: const Text('Limpar seleção'))
                        ]),
                        Text(
                            '${selected.length} de ${catalog.length} países e territórios'),
                        if (selected.isEmpty)
                          const Text(
                              'Nenhum país permitido. Somente as redes explicitamente listadas abaixo poderão entrar.'),
                        const Text(
                            'País desconhecido não é permitido. Selecionar todos não equivale a desabilitar GeoIP.'),
                        SizedBox(
                            height: 210,
                            child: ListView.builder(
                                itemCount: visible.length,
                                itemBuilder: (_, i) => CheckboxListTile(
                                    key: ValueKey('country-${visible[i].code}'),
                                    dense: true,
                                    title: Text(
                                        '${visible[i].name} (${visible[i].code})'),
                                    value: selected.contains(visible[i].code),
                                    onChanged: busy
                                        ? null
                                        : (value) => change(() {
                                              if (value!) {
                                                selected.add(visible[i].code);
                                              } else {
                                                selected
                                                    .remove(visible[i].code);
                                              }
                                            })))),
                        TextField(
                            controller: networks,
                            enabled: !busy,
                            decoration: const InputDecoration(
                                labelText:
                                    'Redes permitidas explicitamente (CIDR, separadas por vírgula)',
                                helperText:
                                    'LAN não é liberada automaticamente. Esta opção não concede acesso administrativo.'),
                            onChanged: (_) => change(() {})),
                      ],
                      SwitchListTile(
                          title: const Text('Limitar taxa de requisições'),
                          value: rate,
                          onChanged: busy
                              ? null
                              : (v) => change(() {
                                    rate = v;
                                  })),
                      if (rate) ...[
                        number('Requisições por segundo', rps),
                        number('Capacidade de burst', burst)
                      ],
                      SwitchListTile(
                          title: const Text('Limitar quota de requisições'),
                          value: quota,
                          onChanged: busy
                              ? null
                              : (v) => change(() {
                                    quota = v;
                                  })),
                      if (quota) ...[
                        number('Requisições admitidas por período', ceiling),
                        DropdownButtonFormField<String>(
                            key:
                                ValueKey('quota-${snapshot!.revision}-$period'),
                            initialValue: period,
                            items: const [
                              DropdownMenuItem(
                                  value: 'day', child: Text('Dia civil UTC')),
                              DropdownMenuItem(
                                  value: 'month', child: Text('Mês civil UTC'))
                            ],
                            onChanged: busy
                                ? null
                                : (v) => change(() {
                                      period = v!;
                                    }))
                      ],
                      const SizedBox(height: 12),
                      const Text(
                          'Rotação de chave, rename e regeneração de URL não zeram consumo. Admissões contam mesmo com erro posterior. '
                          'Os controles não limitam bytes, custo SQL ou mensagens WebSocket; geografia só reavalia novos handshakes. '
                          'Links Storage sem chave usam a política do projeto, não a do slot emissor. A administração autenticada tem orçamento separado.'),
                      TextButton(
                          onPressed: busy ? null : fetchUsage,
                          child: const Text('Consultar consumo atual')),
                      if (usage != null)
                        for (final row in usage!)
                          Text(
                              '${row['period'] == 'day' ? 'Dia' : 'Mês'}: ${row['admitted']} admitidas. Reinicia em ${row['period_end']} (UTC).'),
                      if (usage != null && usage!.isEmpty)
                        const Text(
                            'Nenhuma admissão registrada neste período.'),
                    ],
                  ]))),
          actions: [
            TextButton(
                onPressed: busy
                    ? null
                    : () async {
                        if (await discard() && context.mounted) {
                          Navigator.pop(context);
                        }
                      },
                child: const Text('Fechar')),
            TextButton(
                onPressed: busy
                    ? null
                    : () async {
                        if (await discard()) await load();
                      },
                child: const Text('Recarregar')),
            FilledButton(
                onPressed: busy || snapshot == null || !dirty ? null : save,
                child: const Text('Salvar'))
          ],
        ));
  }
}
