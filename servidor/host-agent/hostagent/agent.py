"""Loop principal do host-agent.

O agent nao expoe porta nenhuma: ele consome intencoes gravadas pela
Projects API na tabela ``host_agent_commands`` (LISTEN/NOTIFY + poll),
faz lease com ``FOR UPDATE SKIP LOCKED``, revalida assinatura HMAC,
argumentos e autorizacao, executa o comando fechado e persiste progresso,
tails sanitizados e resultado. Um heartbeat estende o lease enquanto o
comando roda; o timeout mata o process group.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
import uuid
from typing import Any

import asyncpg

from . import db
from .commands import (
    COMMAND_HANDLERS,
    CommandContext,
    CommandOutcome,
    RunningCommandState,
    container_names,
    match_project,
    docker_ps_all,
)
from .config import AgentConfig
from .host_agent_protocol import (
    COMMAND_TIMEOUTS,
    HOST_AGENT_COMMANDS,
    NOTIFY_CHANNEL,
    evaluate_authorization,
    intent_is_expired,
    sanitize_output,
    validate_command_args,
    verify_command_signature,
)
from .security import PathConfinementError

AGENT_VERSION = "1.0.0"
LEASE_REAP_GRACE_SECONDS = 60

logger = logging.getLogger("hostagent")


class HostAgent:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.pool: asyncpg.Pool | None = None
        self._busy_projects: set[str] = set()
        self._running_tasks: set[asyncio.Task[None]] = set()
        self._wakeup = asyncio.Event()
        self._stopping = asyncio.Event()
        self._listen_conn: asyncpg.Connection | None = None

    async def run(self) -> None:
        assert set(COMMAND_HANDLERS) == HOST_AGENT_COMMANDS, (
            "registro de handlers divergente do protocolo"
        )
        self.pool = await db.create_pool(self.config.dsn)
        await db.register_worker(
            self.pool,
            self.config.worker_id,
            socket.gethostname(),
            os.getpid(),
            AGENT_VERSION,
        )
        logger.info("host-agent iniciado: worker_id=%s", self.config.worker_id)

        await self._start_listener()
        tasks = [
            asyncio.create_task(self._worker_heartbeat_loop(), name="worker-heartbeat"),
            asyncio.create_task(self._state_refresh_loop(), name="state-refresh"),
            asyncio.create_task(self._lease_reaper_loop(), name="lease-reaper"),
            asyncio.create_task(self._lease_loop(), name="lease-loop"),
        ]
        await self._stopping.wait()
        logger.info("encerrando: aguardando comandos em execucao...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._running_tasks:
            done, pending = await asyncio.wait(
                self._running_tasks, timeout=self.config.shutdown_grace
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        if self._listen_conn is not None:
            await self._listen_conn.close()
        await db.mark_worker_stopped(self.pool, self.config.worker_id)
        await self.pool.close()
        logger.info("host-agent finalizado")

    def request_stop(self) -> None:
        self._stopping.set()

    async def _start_listener(self) -> None:
        try:
            self._listen_conn = await asyncpg.connect(self.config.dsn)
            await self._listen_conn.add_listener(
                NOTIFY_CHANNEL, lambda *_args: self._wakeup.set()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LISTEN indisponivel (%s); usando somente polling", exc)
            self._listen_conn = None

    async def _worker_heartbeat_loop(self) -> None:
        while True:
            try:
                await db.heartbeat_worker(self.pool, self.config.worker_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("heartbeat do worker falhou: %s", exc)
            await asyncio.sleep(self.config.heartbeat_interval)

    async def _lease_reaper_loop(self) -> None:
        """Marca como failed comandos cujo lease expirou (agent morto)."""
        while True:
            try:
                await self.pool.execute(
                    """
                    UPDATE host_agent_commands
                    SET status = 'failed',
                        error_code = 'lease_expired',
                        message = 'Lease expirado sem heartbeat do worker.',
                        finished_at = now(),
                        updated_at = now()
                    WHERE status = 'running'
                      AND lease_expires_at < now() - make_interval(secs => $1)
                    """,
                    LEASE_REAP_GRACE_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("reaper de leases falhou: %s", exc)
            await asyncio.sleep(self.config.lease_seconds)

    async def _state_refresh_loop(self) -> None:
        while True:
            try:
                await self._refresh_container_state()
            except Exception as exc:  # noqa: BLE001
                logger.warning("refresh do estado de containers falhou: %s", exc)
            await asyncio.sleep(self.config.state_refresh_interval)

    async def _refresh_container_state(self) -> None:
        projects = await db.fetch_project_names(self.pool)
        if not projects:
            await db.replace_container_state(self.pool, [])
            return
        entries: list[dict[str, str]] = []
        for container in await docker_ps_all():
            names = container_names(container)
            if not names:
                continue
            for project in projects:
                if match_project(container, project):
                    entries.append(
                        {
                            "container_name": names[0],
                            "project": project,
                            "state": container.get("State", ""),
                            "status": container.get("Status", ""),
                            "image": container.get("Image", ""),
                            "ports": container.get("Ports", ""),
                            "created_at_text": container.get("CreatedAt", ""),
                        }
                    )
                    break
        await db.replace_container_state(self.pool, entries)

    async def _lease_loop(self) -> None:
        while True:
            leased = None
            if len(self._running_tasks) < self.config.max_parallel_commands:
                try:
                    leased = await db.lease_next_command(
                        self.pool,
                        self.config.worker_id,
                        self.config.lease_seconds,
                        self._busy_projects,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("lease falhou: %s", exc)
            if leased is not None:
                self._spawn_command(leased)
                continue
            self._wakeup.clear()
            try:
                await asyncio.wait_for(
                    self._wakeup.wait(), timeout=self.config.poll_interval
                )
            except asyncio.TimeoutError:
                pass

    def _spawn_command(self, record: asyncpg.Record) -> None:
        project = record["project"]
        self._busy_projects.add(project)
        task = asyncio.create_task(
            self._execute_command(record), name=f"command:{record['id']}"
        )
        self._running_tasks.add(task)

        def _done(finished: asyncio.Task[None]) -> None:
            self._running_tasks.discard(finished)
            self._busy_projects.discard(project)
            self._wakeup.set()

        task.add_done_callback(_done)

    async def _execute_command(self, record: asyncpg.Record) -> None:
        command_id: uuid.UUID = record["id"]
        command: str = record["command"]
        project: str = record["project"]
        args = record["args"]
        if isinstance(args, str):
            args = json.loads(args)
        args = args or {}

        logger.info("comando %s (%s) leased para %s", command_id, command, project)

        rejection = await self._revalidate(record, command, project, args)
        if rejection is not None:
            code, detail = rejection
            logger.warning("comando %s rejeitado: %s (%s)", command_id, code, detail)
            await db.reject_command(self.pool, command_id, self.config.worker_id, code, detail)
            return

        state = RunningCommandState()
        timeout_seconds = int(record["timeout_seconds"] or COMMAND_TIMEOUTS[command])
        ctx = CommandContext(
            config=self.config,
            state=state,
            timeout_seconds=timeout_seconds,
            command=command,
        )
        heartbeat = asyncio.create_task(self._command_heartbeat_loop(command_id, state))
        try:
            outcome = await COMMAND_HANDLERS[command](ctx, project, args)
        except PathConfinementError as exc:
            outcome = CommandOutcome(
                status="failed",
                error_code=f"path_confinement:{exc.code}",
                message="Path fora do diretorio raiz de projetos.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("comando %s falhou inesperadamente", command_id)
            outcome = CommandOutcome(
                status="failed",
                error_code="agent_internal_error",
                message="Falha interna inesperada no host-agent.",
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

        persisted = await db.finish_command(
            self.pool,
            command_id,
            self.config.worker_id,
            status=outcome.status,
            exit_code=outcome.exit_code,
            error_code=outcome.error_code,
            stdout_tail=state.stdout_tail(),
            stderr_tail=state.stderr_tail(),
            result=outcome.result,
            message=outcome.message,
        )
        if not persisted:
            logger.warning(
                "comando %s terminou (%s) mas o registro ja estava finalizado",
                command_id,
                outcome.status,
            )
        try:
            await self._refresh_container_state()
        except Exception:  # noqa: BLE001
            pass
        if outcome.status == "failed":
            logger.warning(
                "comando %s (%s) falhou: %s — %s",
                command_id,
                command,
                outcome.error_code or "sem_codigo",
                sanitize_output(outcome.message or "", tail_limit=400) or "sem mensagem",
            )
        logger.info("comando %s finalizado: %s", command_id, outcome.status)

    async def _command_heartbeat_loop(self, command_id: uuid.UUID, state: RunningCommandState) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    state.progress_changed.wait(),
                    timeout=self.config.heartbeat_interval,
                )
            except asyncio.TimeoutError:
                pass
            state.progress_changed.clear()
            try:
                await db.heartbeat_command(
                    self.pool,
                    command_id,
                    self.config.worker_id,
                    self.config.lease_seconds,
                    stdout_tail=state.stdout_tail() if state.dirty else None,
                    stderr_tail=state.stderr_tail() if state.dirty else None,
                    progress=state.progress,
                    current_step=state.current_step,
                    message=state.message,
                )
                state.dirty = False
            except Exception as exc:  # noqa: BLE001
                logger.warning("heartbeat do comando %s falhou: %s", command_id, exc)

    async def _revalidate(
        self,
        record: asyncpg.Record,
        command: str,
        project: str,
        args: dict[str, Any],
    ) -> tuple[str, str] | None:
        """Fail-closed: assinatura HMAC, argumentos e autorizacao."""
        if not verify_command_signature(
            self.config.hmac_secret,
            record["signature"],
            command_id=str(record["id"]),
            command=command,
            project=project,
            project_uuid=str(record["project_uuid"]) if record["project_uuid"] else None,
            requested_by=str(record["requested_by"]) if record["requested_by"] else None,
            args=args,
            issued_at=record["issued_at"],
        ):
            return ("signature_invalid", "Assinatura HMAC da intencao nao confere.")

        if intent_is_expired(record["issued_at"]):
            return (
                "intent_expired",
                "Intencao assinada excedeu a janela maxima de validade.",
            )

        arg_errors = validate_command_args(command, project, args)
        if arg_errors:
            return ("invalid_args", "; ".join(arg_errors))

        auth = await db.load_authorization_context(
            self.pool,
            project=project,
            requested_by=record["requested_by"],
        )
        project_uuid_matches = True
        if record["project_uuid"] is not None and auth["project_id"] is not None:
            project_uuid_matches = auth["project_id"] == record["project_uuid"]
        denial = evaluate_authorization(
            command,
            user_exists=auth["user_exists"],
            user_active=auth["user_active"],
            is_global_admin=auth["is_global_admin"],
            is_owner=auth["is_owner"],
            member_role=auth["member_role"],
            project_row_exists=auth["project_row_exists"],
            project_uuid_matches=project_uuid_matches,
        )
        if denial is not None:
            return (f"authorization_denied:{denial}", "Reautorizacao no agent negou o comando.")
        return None


async def run_agent(config: AgentConfig) -> None:
    agent = HostAgent(config)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, agent.request_stop)
        except NotImplementedError:
            # Windows/dev: sem signal handlers; Ctrl+C vira KeyboardInterrupt.
            pass
    await agent.run()
