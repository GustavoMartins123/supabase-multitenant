# Host-agent

Documento canônico do host-agent: o serviço que executa, no host do
servidor principal, todo o lifecycle físico dos projetos (Docker e
scripts). Depois desta fronteira, a Projects API **não executa Docker nem
shell** — ela apenas grava intenções no banco.

## Fluxo

```text
Projects API (container)
    | grava intenção assinada (HMAC) em host_agent_commands + NOTIFY
    v
Postgres do control plane
    ^
    | LISTEN/NOTIFY + poll, lease com FOR UPDATE SKIP LOCKED
    |
host-agent (systemd, no host, com Docker)
    | revalida assinatura, argumentos e autorização
    | executa o comando fechado (docker/compose/scripts)
    | heartbeat estende o lease; timeout mata o process group
    v
progresso, tails sanitizados e resultado de volta na mesma linha
```

A Projects API espera o desfecho na própria linha (`wait_command`),
espelhando progresso no job correspondente. A fila FIFO por projeto da API
continua valendo; o agent também recusa dois comandos simultâneos do mesmo
projeto no lease.

## Conjunto fechado de comandos

Definido em `host_agent_protocol.py` (cópias idênticas na API e no agent,
verificadas por teste):

| Comando | Executa | Timeout |
| --- | --- | --- |
| `start_project` / `stop_project` / `restart_project` | docker start/stop/restart por container do projeto | 600s |
| `recreate_services` | aplica settings do tenant Storage pela Admin API e/ou recria somente serviços locais solicitados | 1800s |
| `ensure_opaque_gateway_token` | valida ou gera o token interno exclusivo do gateway sem imprimi-lo | 120s |
| `stage_opaque_gateway` | para o Nginx legado e materializa o template opaco | 600s |
| `create_project` | `generate_project.sh` | 1800s |
| `duplicate_project` | `duplicate_project.sh` | 3600s |
| `delete_project_containers` | `docker rm -f` dos containers do projeto | 300s |
| `delete_project_storage` | revoga credenciais, remove tenant e namespace UUID do Storage global | 600s |
| `delete_project_files` | `delete_project.sh` | 300s |
| `rotate_keys` | `rotate_key.sh` | 900s |
| `rename_project` | `rename_project.sh` (TERM grace de 240s p/ rollback) | 3600s |
| `backup_project` | `backup_project.sh` (captura banco + somente o namespace Storage do UUID) | 1800s |
| `restore_project` | `restore_project.sh` (cria ponto de segurança, troca banco e somente o namespace do tenant; TERM grace de 240s p/ rollback) | 3600s |
| `delete_restore_point` | remoção confinada do diretório do ponto | 120s |
| `container_logs` | docker inspect + logs, saída sanitizada | 60s |

Não existe comando que aceite argv, path ou SQL arbitrário. Os comandos de
ponto de restauração recebem apenas UUIDs validados nos dois lados; o path resolvido fica confinado a `servidor/backups/<tenant_uuid>/`, onde o
`tenant_uuid` é recebido do control plane e precisa coincidir com o
`PROJECT_UUID` do `.env`. Em projetos novos ele equivale a `projects.id`;
instalações anteriores são convertidas uma vez e passam pelo mesmo contrato,
sem caminho alternativo no runtime. Criar um ponto frio
(`backup_project`) exige admin do projeto, owner ou admin global. Restaurar e
excluir pontos (`PROJECT_OWNER_COMMANDS`) exigem owner ou admin global.

## Segurança

1. **HMAC fail-closed** — cada intenção é assinada pela API com
   `HOST_AGENT_HMAC_SECRET` sobre (id, comando, projeto, project UUID,
   solicitante, hash canônico dos args, issued_at). O agent recusa
   assinatura inválida; um escritor arbitrário no Postgres não consegue
   forjar execução no host.
2. **Reautorização no agent** — o agent reconsulta `users`, `user_groups`,
   `projects` e `project_members` e aplica a mesma matriz da API:
   admin global para o fluxo de exclusão integral do projeto; owner ou admin
   global para restaurar/excluir pontos; owner, admin
   do projeto ou admin global para os demais comandos. O `project_uuid` da intenção
   precisa bater com `projects.id` (exceto nos passos do delete que rodam
   após a remoção da linha); quando os args carregam `tenant_uuid`, ele também
   precisa bater com `projects.tenant_uuid`.
   A única intenção sem usuário é `rotate_keys` com
   `args.trigger=automatic`; ela só é aceita quando
   `projects.automatic_key_rotation_enabled=true`. Qualquer outro comando de
   sistema é recusado.
3. **Paths confinados** — nomes passam pela mesma regex/reservas da API e
   o path resolvido precisa ficar sob `servidor/projects`; componentes
   symlink e traversal são rejeitados antes de qualquer script.
4. **Saída sanitizada** — stdout/stderr passam por redação (JWTs,
   `CHAVE=valor` sensível, credenciais em URI, Bearer) antes de qualquer
   persistência; as chaves de projeto não passam mais por stdout — a API
   as lê do `.env` do projeto após o comando.
5. **Lease, heartbeat e timeout** — lease de 60s renovado a cada 15s;
   comandos com lease expirado são marcados `failed` (`lease_expired`);
   timeout duro por comando com SIGTERM → SIGKILL no process group.

## Estado de containers

O agent mantém `project_container_state` (snapshot de `docker ps` por
projeto, ~10s). Os endpoints de status da API leem essa tabela; sem
heartbeat de agent há 45s a API responde `503`/estado `unknown` em vez de
mentir.

## Recuperação

- API reiniciada no meio de um comando: o agent continua executando; o
  recovery religa o job na mesma intenção (`job_id` + comando) e finaliza
  com o resultado persistido. Rename e rotação de chaves são retomáveis por
  esse mecanismo sem disparar um segundo script.
- Agent reiniciado no meio de um comando: o lease expira, a linha vira
  `failed (lease_expired)` e o job falha com esse código.
- Agent offline: intenções em fila são canceladas após 60s sem worker e a
  API responde `host_agent_offline`.

## Operação

```bash
sudo bash servidor/host-agent/install.sh   # venv + systemd + enable/start
journalctl -u supabase-host-agent -f
```

Configuração e requisitos do host: `servidor/host-agent/README.md`.

## Código relacionado

- `servidor/host-agent/hostagent/` (agent)
- `servidor/api-internal/app/host_agent.py` (cliente e schema)
- `servidor/api-internal/app/host_agent_protocol.py` (contrato compartilhado)
- `tests/smoke/test_host_agent_contract.py` (contrato fixado em teste)
