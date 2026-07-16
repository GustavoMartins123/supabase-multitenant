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
| `recreate_services` | templates + `docker compose up -d --force-recreate` | 1800s |
| `create_project` | `generate_project.sh` | 1800s |
| `duplicate_project` | `duplicate_project.sh` | 3600s |
| `delete_project_containers` | `docker rm -f` dos containers do projeto | 300s |
| `delete_project_files` | `delete_project.sh` | 300s |
| `rotate_keys` | `rotate_key.sh` | 900s |
| `rename_project` | `rename_project.sh` (TERM grace de 240s p/ rollback) | 3600s |
| `backup_project` | `backup_project.sh` (ponto de restauração frio: para os serviços do projeto, captura banco + storage em `servidor/backups/<uuid>/<id>/`, religa) | 1800s |
| `restore_project` | `restore_project.sh` (cria ponto de segurança, troca banco e storage; TERM grace de 240s p/ rollback) | 3600s |
| `delete_restore_point` | remoção confinada do diretório do ponto | 120s |
| `container_logs` | docker inspect + logs, saída sanitizada | 60s |
| `terminate_supavisor_tenant` / `delete_supavisor_tenant` / `delete_realtime_tenant` | curl dentro do container do serviço, token construído localmente | 60s |

Não existe comando que aceite argv, path ou SQL arbitrário. Os comandos de
ponto de restauração recebem apenas UUIDs validados nos dois lados; o path resolvido fica confinado a `servidor/backups/<tenant_uuid>/`, onde o
`tenant_uuid` é o `PROJECT_UUID` lido do `.env` do projeto (imutável no
rename, distinto do `projects.id` do control plane). Diferente do restante
do lifecycle, eles são autorizados para qualquer membro do projeto
(`PROJECT_MEMBER_COMMANDS`), além de owner e admin global.

## Segurança

1. **HMAC fail-closed** — cada intenção é assinada pela API com
   `HOST_AGENT_HMAC_SECRET` sobre (id, comando, projeto, project UUID,
   solicitante, hash canônico dos args, issued_at). O agent recusa
   assinatura inválida; um escritor arbitrário no Postgres não consegue
   forjar execução no host.
2. **Reautorização no agent** — o agent reconsulta `users`, `user_groups`,
   `projects` e `project_members` e aplica a mesma matriz da API:
   admin global para o fluxo de delete e limpeza de tenants; owner, admin
   do projeto ou admin global para o restante. O `project_uuid` da intenção
   precisa bater com `projects.id` (exceto nos passos do delete que rodam
   após a remoção da linha).
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
  com o resultado persistido. Rename voltou a ser retomável por esse
  mecanismo.
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
