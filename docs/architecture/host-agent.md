# Host-agent

Canonical host-agent document: the service that runs the projects' entire
physical lifecycle (Docker and scripts) on the main server host. Beyond this
boundary, the Projects API **does not execute Docker or a shell** — it only
writes intents to the database.

## Flow

```text
Projects API (container)
    | writes signed intent (HMAC) to host_agent_commands + NOTIFY
    v
Control-plane Postgres
    ^
    | LISTEN/NOTIFY + poll, lease with FOR UPDATE SKIP LOCKED
    |
host-agent (systemd, on host, with Docker)
    | revalidates signature, arguments, and authorization
    | executes the closed command (docker/compose/scripts)
    | heartbeat extends the lease; timeout kills the process group
    v
progress, sanitized tails, and result back on the same row
```

The Projects API waits for the outcome on the same row (`wait_command`),
mirroring progress into the corresponding job. The API's per-project FIFO
queue remains in effect; the agent also rejects two simultaneous commands for
the same project during lease acquisition.

## Closed command set

Defined in `host_agent_protocol.py` (identical copies in the API and agent,
verified by a test):

| Command | Executes | Timeout |
| --- | --- | --- |
| `start_project` / `stop_project` / `restart_project` | docker start/stop/restart per project container | 600s |
| `recreate_services` | applies Storage tenant settings through the Admin API and/or recreates only requested local services | 1800s |
| `ensure_opaque_gateway_token` | validates or generates the gateway-exclusive internal token without printing it | 120s |
| `stage_opaque_gateway` | stops the legacy Nginx and materializes the opaque template | 600s |
| `create_project` | `generate_project.sh` | 1800s |
| `duplicate_project` | `duplicate_project.sh` | 3600s |
| `delete_project_containers` | `docker rm -f` for project containers | 300s |
| `delete_project_storage` | revokes credentials and removes the tenant and UUID namespace from global Storage | 600s |
| `delete_project_files` | `delete_project.sh` | 300s |
| `rotate_keys` | `rotate_key.sh` | 900s |
| `rename_project` | `rename_project.sh` (240s TERM grace for rollback) | 3600s |
| `backup_project` | `backup_project.sh` (captures the database and only the UUID's Storage namespace) | 1800s |
| `restore_project` | `restore_project.sh` (creates a safety point, swaps the database and only the tenant namespace; 240s TERM grace for rollback) | 3600s |
| `delete_restore_point` | confined removal of the point directory | 120s |
| `container_logs` | docker inspect + logs, sanitized output | 60s |

No command accepts arbitrary argv, paths, or SQL. Restore-point commands receive
only UUIDs validated on both sides; the resolved path is confined to
`servidor/backups/<tenant_uuid>/`, where `tenant_uuid` is received from the
control plane and must match the project's `PROJECT_UUID` in `.env`. For new
projects it equals `projects.id`; older installations are converted once and
use the same contract, with no alternate runtime path. Creating a cold point
(`backup_project`) requires a project admin, owner, or global admin. Restoring
and deleting points (`PROJECT_OWNER_COMMANDS`) require an owner or global
admin.

## Security

1. **HMAC fail-closed** — each intent is signed by the API with
   `HOST_AGENT_HMAC_SECRET` over (id, command, project, project UUID,
   requester, canonical args hash, issued_at). The agent rejects an invalid
   signature; an arbitrary PostgreSQL writer cannot forge host execution.
2. **Reauthorization in the agent** — the agent re-queries `users`,
   `user_groups`, `projects`, and `project_members` and applies the same API
   matrix: global admin for full project deletion; owner or global admin for
   restoring/deleting points; owner, project admin, or global admin for other
   commands. The intent's `project_uuid` must match `projects.id` (except for
   delete steps that run after the row is removed); when args carry
   `tenant_uuid`, it must also match `projects.tenant_uuid`.
   The only userless intent is `rotate_keys` with
   `args.trigger=automatic`; it is accepted only when
   `projects.automatic_key_rotation_enabled=true`. Any other system command is
   rejected.
3. **Confined paths** — names pass the same API regex/reservations and the
   resolved path must remain under `servidor/projects`; symlink and traversal
   components are rejected before any script.
4. **Sanitized output** — stdout/stderr is redacted (JWTs, sensitive
   `KEY=value`, URI credentials, Bearer) before persistence; project keys are
   no longer written to stdout — the API reads them from the project's
   `.env` after the command.
5. **Lease, heartbeat, and timeout** — a 60s lease renewed every 15s; commands
   with an expired lease are marked `failed` (`lease_expired`); hard
   per-command timeout with SIGTERM → SIGKILL on the process group.

## Container state

The agent maintains `project_container_state` (a per-project `docker ps`
snapshot, ~10s). API status endpoints read this table; without an agent
heartbeat for 45s, the API responds with `503`/state `unknown` instead of
lying.

## Recovery

- API restarted in the middle of a command: the agent continues executing;
  recovery reconnects the job to the same intent (`job_id` + command) and
  finishes with the persisted result. Rename and key rotation can resume
  through this mechanism without launching a second script.
- Agent restarted in the middle of a command: the lease expires, the row
  becomes `failed (lease_expired)`, and the job fails with that code.
- Agent offline: queued intents are canceled after 60s without a worker and the
  API responds with `host_agent_offline`.

## Operations

```bash
sudo bash servidor/host-agent/install.sh   # venv + systemd + enable/start
journalctl -u supabase-host-agent -f
```

Host configuration and requirements: `servidor/host-agent/README.md`.

## Related code

- `servidor/host-agent/hostagent/` (agent)
- `servidor/api-internal/app/host_agent.py` (client; the schema comes from [control-plane migrations](control-plane-migrations.md))
- `servidor/api-internal/app/host_agent_protocol.py` (shared contract)
- `tests/smoke/test_host_agent_contract.py` (contract fixed by a test)
