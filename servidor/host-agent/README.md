# Host-agent

Serviço que roda **no host** do servidor principal e executa um conjunto
fechado de comandos de lifecycle (start/stop/restart, recreate, create,
duplicate, delete, rotate, rename, logs e limpeza de tenants). Ele substitui
o acesso da Projects API ao Docker: a API grava a **intenção** na tabela
`host_agent_commands`, o agent obtém o **lease** e executa.

## Modelo de segurança

- **Comandos fechados**: nenhum argv chega pronto do banco; os handlers
  montam a linha de comando localmente a partir de argumentos validados
  (`hostagent/host_agent_protocol.py`).
- **HMAC**: cada intenção é assinada pela API com `HOST_AGENT_HMAC_SECRET`.
  O agent recusa assinatura inválida (fail-closed), então um escritor
  arbitrário no Postgres não consegue forjar execução no host.
- **Reautorização**: antes de executar, o agent reconsulta `users`,
  `user_groups`, `projects` e `project_members` e aplica a mesma matriz de
  autorização da API (admin global para o fluxo de delete; owner/admin do
  projeto para o restante).
- **Paths confinados**: qualquer path derivado de comando é resolvido sob
  `servidor/projects`; symlinks e traversal são rejeitados
  (`hostagent/security.py`).
- **Saída sanitizada**: stdout/stderr passam por redação de JWTs, senhas,
  tokens e credenciais em URI antes de qualquer persistência.
- **Lease/heartbeat/timeout**: lease com `FOR UPDATE SKIP LOCKED`
  serializado por projeto, heartbeat que estende o lease, timeout duro por
  comando com `SIGTERM` (grace maior para rename, que faz rollback) e
  `SIGKILL`. Um reaper marca como `failed` comandos com lease expirado.

## Requisitos do host

- Linux com systemd, Docker e Compose v2.
- `bash`, `jq`, `rsync`, `openssl` (dependências dos scripts de lifecycle).
- Python >= 3.10.
- Rede: o agent conecta no Postgres do control plane pelo IP fixo da
  bridge `rede-supabase` (`POSTGRES_HOST` do `servidor/.env`).

## Instalação

```bash
# depois de rodar o setup.sh (que gera HOST_AGENT_HMAC_SECRET):
sudo bash servidor/host-agent/install.sh
journalctl -u supabase-host-agent -f
```

O comando pode ser executado da raiz do repositorio ou de outro diretorio; o
instalador resolve o pacote local `hostagent` pelo proprio diretorio.

O instalador aguarda brevemente as tabelas criadas pela Projects API. Em uma
instalação limpa na qual a API ainda não subiu, ele deixa o serviço habilitado
sem iniciá-lo. O `start.sh` sobe a API e inicia o serviço; o `ExecStartPre` da
unit aguarda o schema ficar pronto, evitando reinícios com
`UndefinedTableError`.

Para rodar em foreground durante desenvolvimento:

```bash
cd servidor/host-agent
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m hostagent --root "$(pwd)/.." --verbose
```

## Configuração

Tudo é lido de `servidor/.env` (ou variáveis de ambiente com o mesmo nome):

| Variável | Default | Uso |
| --- | --- | --- |
| `HOST_AGENT_HMAC_SECRET` | — (obrigatória) | Assinatura das intenções. |
| `HOST_AGENT_DB_DSN` | derivada de `POSTGRES_*` | Override do DSN. |
| `HOST_AGENT_POLL_INTERVAL` | `2.0` | Poll de fallback (LISTEN/NOTIFY é o caminho rápido). |
| `HOST_AGENT_HEARTBEAT_INTERVAL` | `15.0` | Heartbeat de worker e de comando. |
| `HOST_AGENT_LEASE_SECONDS` | `60` | Duração do lease. |
| `HOST_AGENT_STATE_REFRESH_INTERVAL` | `10.0` | Snapshot de containers por projeto. |
| `HOST_AGENT_MAX_PARALLEL_COMMANDS` | `3` | Comandos simultâneos (nunca 2 do mesmo projeto). |
| `HOST_AGENT_SHUTDOWN_GRACE` | `300` | Espera por comandos em execução no stop. |
| `HOST_AGENT_SCHEMA_WAIT_TIMEOUT` | `180` | Espera da unit pelas tabelas criadas pela Projects API. |

Para alterar apenas a espera curta feita durante a instalação, exporte
`HOST_AGENT_INSTALL_SCHEMA_WAIT_TIMEOUT` (default: `15` segundos).

## Tabelas (criadas pela Projects API)

- `host_agent_commands` — intenções, lease, progresso, tails e resultado.
- `host_agent_workers` — heartbeat dos agents (a API considera o agent
  offline sem heartbeat há 45s).
- `project_container_state` — snapshot dos containers por projeto usado
  pelos endpoints de status da API.
