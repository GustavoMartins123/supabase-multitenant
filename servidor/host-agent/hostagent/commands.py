"""Conjunto fechado de comandos executados pelo host-agent.

Cada comando e um handler registrado em ``COMMAND_HANDLERS``. Nao existe
caminho para executar argv arbitrario: os handlers montam a linha de
comando localmente a partir de argumentos validados pelo protocolo e de
paths confinados ao diretorio raiz de projetos.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac as hmac_module
import json
import os
import re
import shutil
import signal
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from .config import AgentConfig
from .envfile import read_env_file
from .host_agent_protocol import (
    COMMAND_TERM_GRACE,
    CONTAINER_LOGS_LIMIT,
    DEFAULT_TERM_GRACE,
    is_valid_uuid,
    sanitize_output,
)
from .security import (
    PathConfinementError,
    resolve_backup_dir,
    resolve_backup_project_dir,
    resolve_project_dir,
)
from .templates import sync_project_generated_files

PROJECT_SERVICE_ORDER = ["meta", "auth", "rest", "imgproxy", "storage", "nginx"]
TENANT_API_ACCEPTED_STATUSES = {200, 202, 204, 404}
SUPAVISOR_CONTAINER = "supabase-pooler"
REALTIME_CONTAINER = "realtime-dev.supabase-realtime"
_OUTPUT_WINDOW_LIMIT = 64_000


@dataclass
class CommandOutcome:
    status: str
    exit_code: int | None = None
    error_code: str | None = None
    result: dict[str, Any] | None = None
    message: str | None = None


@dataclass
class RunningCommandState:
    """Estado em memoria compartilhado com o loop de heartbeat."""

    progress: int = 0
    current_step: str | None = None
    message: str | None = None
    _stdout: str = ""
    _stderr: str = ""
    dirty: bool = field(default=False)

    def report(
        self,
        *,
        progress: int | None = None,
        step: str | None = None,
        message: str | None = None,
    ) -> None:
        if progress is not None:
            self.progress = max(0, min(100, progress))
        if step is not None:
            self.current_step = step
        if message is not None:
            self.message = message
        self.dirty = True

    def append_output(self, stream: str, text: str) -> None:
        if stream == "stderr":
            self._stderr = (self._stderr + text)[-_OUTPUT_WINDOW_LIMIT:]
        else:
            self._stdout = (self._stdout + text)[-_OUTPUT_WINDOW_LIMIT:]
        self.dirty = True

    def stdout_tail(self) -> str:
        return sanitize_output(self._stdout)

    def stderr_tail(self) -> str:
        return sanitize_output(self._stderr)


@dataclass
class CommandContext:
    config: AgentConfig
    state: RunningCommandState
    timeout_seconds: int
    command: str


@dataclass
class ProcessResult:
    returncode: int | None
    timed_out: bool
    markers_seen: set[str]


async def _pump_stream(reader: asyncio.StreamReader | None, state: RunningCommandState, stream: str, markers: tuple[str, ...], seen: set[str]) -> None:
    if reader is None:
        return
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            return
        state.append_output(stream, chunk.decode(errors="replace"))
        if markers:
            window = state._stdout if stream == "stdout" else state._stderr
            for marker in markers:
                if marker in window:
                    seen.add(marker)


async def run_process(
    argv: list[str],
    ctx: CommandContext,
    *,
    cwd: Path | None = None,
    markers: tuple[str, ...] = (),
) -> ProcessResult:
    """Executa um processo com captura incremental, timeout e killpg."""
    term_grace = COMMAND_TERM_GRACE.get(ctx.command, DEFAULT_TERM_GRACE)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    seen: set[str] = set()
    pumps = asyncio.gather(
        _pump_stream(proc.stdout, ctx.state, "stdout", markers, seen),
        _pump_stream(proc.stderr, ctx.state, "stderr", markers, seen),
    )
    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=ctx.timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
        _terminate_process_group(proc, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=term_grace)
        except asyncio.TimeoutError:
            _terminate_process_group(proc, signal.SIGKILL)
            await proc.wait()
    finally:
        try:
            await asyncio.wait_for(pumps, timeout=10)
        except asyncio.TimeoutError:
            pumps.cancel()
    return ProcessResult(proc.returncode, timed_out, seen)


def _terminate_process_group(proc: asyncio.subprocess.Process, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass


async def _run_short(argv: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", "timeout"
    return (
        proc.returncode if proc.returncode is not None else 1,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


async def docker_ps_all() -> list[dict[str, Any]]:
    code, stdout, stderr = await _run_short(
        ["docker", "ps", "--format", "{{json .}}", "-a"]
    )
    if code != 0:
        raise RuntimeError(f"docker ps falhou: {stderr.strip() or code}")
    containers: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            containers.append(json.loads(line))
    return containers


def container_names(entry: Mapping[str, Any]) -> list[str]:
    names = entry.get("Names", "")
    if isinstance(names, str):
        return [name for name in names.split(",") if name]
    return list(names)


def match_project(entry: Mapping[str, Any], project: str) -> bool:
    pattern = re.compile(rf"-{re.escape(project)}$")
    return any(pattern.search(name) for name in container_names(entry))


async def list_project_containers(project: str) -> list[dict[str, Any]]:
    return [entry for entry in await docker_ps_all() if match_project(entry, project)]


def _service_priority(name: str) -> int:
    lowered = name.lower()
    for index, service in enumerate(PROJECT_SERVICE_ORDER):
        if service in lowered:
            return index
    return 999


def sort_project_containers(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        containers,
        key=lambda entry: _service_priority(",".join(container_names(entry))),
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _hs256_jwt(payload: dict[str, Any], secret: str) -> str:
    header_b64 = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac_module.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def _short_lived_jwt(secret: str, issuer: str) -> str:
    now = int(time.time())
    return _hs256_jwt(
        {"role": "anon", "iss": issuer, "iat": now, "exp": now + 3600},
        secret,
    )


def _load_project_env(ctx: CommandContext, project: str) -> dict[str, str]:
    try:
        project_dir = resolve_project_dir(ctx.config.projects_root, project)
    except PathConfinementError:
        return {}
    return read_env_file(project_dir / ".env")


def _tenant_external_id(project_env: dict[str, str], project: str) -> str:
    return project_env.get("PROJECT_UUID", "").strip() or project


async def _tenant_curl(
    container: str,
    method: str,
    path: str,
    token: str,
) -> tuple[int | None, str]:
    argv = [
        "docker", "exec", container,
        "curl", "-sS", "-w", "\n%{http_code}",
    ]
    if method != "GET":
        argv += ["-X", method]
    argv += [f"http://localhost:4000{path}", "-H", f"Authorization: Bearer {token}"]
    code, stdout, stderr = await _run_short(argv, timeout=30.0)
    if code != 0:
        return None, (stderr or stdout or f"codigo {code}")[:300]
    body, separator, status_text = stdout.rpartition("\n")
    if not separator:
        return None, stdout[:300]
    try:
        return int(status_text.strip()), body.strip()[:300]
    except ValueError:
        return None, stdout[:300]


async def _container_action(
    ctx: CommandContext,
    project: str,
    *,
    verb: str,
    argv_builder: Callable[[str], list[str]],
    skip: Callable[[Mapping[str, Any]], bool],
    settle_seconds: float = 0.0,
    allow_empty: bool = False,
) -> CommandOutcome:
    containers = sort_project_containers(await list_project_containers(project))
    if not containers and not allow_empty:
        return CommandOutcome(
            status="failed",
            error_code="containers_missing",
            message=f"Nenhum container encontrado para o projeto {project}.",
        )

    touched: list[str] = []
    errors: list[str] = []
    total = max(len(containers), 1)
    for index, entry in enumerate(containers, start=1):
        names = container_names(entry)
        if not names:
            continue
        name = names[0]
        ctx.state.report(
            progress=min(95, int(index * 95 / total)),
            step=f"{verb}:{name}",
            message=f"{verb} ({index}/{total})...",
        )
        if skip(entry):
            touched.append(f"{name} (skipped)")
            continue
        code, _, stderr = await _run_short(argv_builder(name), timeout=120.0)
        if code == 0:
            touched.append(name)
            if settle_seconds:
                await asyncio.sleep(settle_seconds)
        else:
            errors.append(f"{verb} {name}: {sanitize_output(stderr.strip(), tail_limit=300)}")

    result = {"containers": touched, "errors": errors}
    if errors:
        return CommandOutcome(
            status="failed",
            error_code=f"{ctx.command}_failed",
            result=result,
            message="\n".join(errors),
        )
    return CommandOutcome(status="done", result=result)


async def handle_start_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    return await _container_action(
        ctx,
        project,
        verb="start",
        argv_builder=lambda name: ["docker", "start", name],
        skip=lambda entry: entry.get("State", "") == "running",
        settle_seconds=2.0,
    )


async def handle_stop_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    return await _container_action(
        ctx,
        project,
        verb="stop",
        argv_builder=lambda name: ["docker", "stop", name],
        skip=lambda entry: entry.get("State", "") != "running",
    )


async def handle_restart_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    return await _container_action(
        ctx,
        project,
        verb="restart",
        argv_builder=lambda name: ["docker", "restart", "-t", "30", name],
        skip=lambda entry: False,
        settle_seconds=2.0,
    )


async def handle_delete_project_containers(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    return await _container_action(
        ctx,
        project,
        verb="remove",
        argv_builder=lambda name: ["docker", "rm", "-f", name],
        skip=lambda entry: False,
        allow_empty=True,
    )


async def handle_recreate_services(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    services = [str(service) for service in args["services"]]
    project_dir = resolve_project_dir(ctx.config.projects_root, project, must_exist=True)

    touches_nginx = "nginx" in services
    if touches_nginx:
        ctx.state.report(progress=10, step="render_templates", message="Regenerando templates do projeto...")
        sync_project_generated_files(
            root=ctx.config.root,
            scripts_dir=ctx.config.scripts_dir,
            project_dir=project_dir,
            project=project,
        )

    ctx.state.report(progress=30, step="compose_up", message=f"Recriando servicos: {', '.join(services)}")
    argv = [
        "docker", "compose",
        "-p", project,
        "--env-file", "../../.env",
        "--env-file", ".env",
        "up", "-d",
    ]
    if touches_nginx:
        argv.append("--build")
    argv.append("--force-recreate")
    argv += services

    outcome = await run_process(argv, ctx, cwd=project_dir)
    if outcome.timed_out:
        return CommandOutcome(status="failed", error_code="timeout", exit_code=outcome.returncode)
    if outcome.returncode != 0:
        return CommandOutcome(
            status="failed",
            error_code="recreate_failed",
            exit_code=outcome.returncode,
            message="Erro no recreate; consulte stderr_tail.",
        )
    return CommandOutcome(status="done", exit_code=0, result={"recreated_services": services})


async def _run_lifecycle_script(
    ctx: CommandContext,
    script_name: str,
    script_args: list[str],
    *,
    error_code: str,
    markers: tuple[str, ...] = (),
) -> tuple[CommandOutcome, ProcessResult]:
    script = ctx.config.scripts_dir / script_name
    if not script.is_file():
        return (
            CommandOutcome(
                status="failed",
                error_code="script_missing",
                message=f"Script nao encontrado: {script}",
            ),
            ProcessResult(None, False, set()),
        )
    result = await run_process(
        ["bash", str(script), *script_args],
        ctx,
        cwd=ctx.config.root,
        markers=markers,
    )
    if result.timed_out:
        return (
            CommandOutcome(status="failed", error_code="timeout", exit_code=result.returncode),
            result,
        )
    if result.returncode != 0:
        return (
            CommandOutcome(status="failed", error_code=error_code, exit_code=result.returncode),
            result,
        )
    return CommandOutcome(status="done", exit_code=0), result


async def handle_create_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    resolve_project_dir(ctx.config.projects_root, project)
    ctx.state.report(progress=10, step="provision_infrastructure", message="Provisionando infraestrutura do projeto...")
    outcome, _ = await _run_lifecycle_script(
        ctx,
        "generate_project.sh",
        [project, str(args["tenant_uuid"])],
        error_code="provision_failed",
    )
    return outcome


async def handle_duplicate_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    original = str(args["original_name"])
    resolve_project_dir(ctx.config.projects_root, original, must_exist=True)
    resolve_project_dir(ctx.config.projects_root, project)
    ctx.state.report(progress=10, step="duplicate_infrastructure", message="Duplicando infraestrutura e banco...")
    outcome, _ = await _run_lifecycle_script(
        ctx,
        "duplicate_project.sh",
        [original, project, str(args["copy_mode"]), str(args["tenant_uuid"])],
        error_code="duplicate_failed",
    )
    return outcome


async def handle_delete_project_files(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    resolve_project_dir(ctx.config.projects_root, project)
    outcome, _ = await _run_lifecycle_script(
        ctx,
        "delete_project.sh",
        [project],
        error_code="delete_files_failed",
    )
    project_uuid = str(args.get("project_uuid") or "").strip()
    if outcome.status == "done" and project_uuid:
        removed = await _remove_backup_tree(
            resolve_backup_project_dir(ctx.config.backups_root, project_uuid)
        )
        outcome.result = {**(outcome.result or {}), "backups_removed": removed}
    return outcome


async def handle_rotate_keys(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    resolve_project_dir(ctx.config.projects_root, project, must_exist=True)
    ctx.state.report(progress=10, step="rotate_keys", message="Rotacionando chaves...")
    outcome, _ = await _run_lifecycle_script(
        ctx,
        "rotate_key.sh",
        [project],
        error_code="rotate_script_failed",
    )
    return outcome


async def handle_rename_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    new_name = str(args["new_name"])
    resolve_project_dir(ctx.config.projects_root, project)
    resolve_project_dir(ctx.config.projects_root, new_name)
    ctx.state.report(progress=5, step="migrate_infrastructure", message=f"Renomeando {project} -> {new_name}...")
    outcome, process = await _run_lifecycle_script(
        ctx,
        "rename_project.sh",
        [project, new_name],
        error_code="rename_failed",
        markers=("ROLLBACK_COMPLETE",),
    )
    rolled_back = "ROLLBACK_COMPLETE" in process.markers_seen
    outcome.result = {**(outcome.result or {}), "rolled_back": rolled_back}
    if outcome.status == "failed" and outcome.error_code == "rename_failed" and rolled_back:
        outcome.error_code = "rename_rolled_back"
    return outcome


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return total
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


async def _remove_backup_tree(path: Path) -> bool:
    if not path.exists():
        return False
    await asyncio.to_thread(shutil.rmtree, path, True)
    return not path.exists()


def _resolve_backup_context(
    ctx: CommandContext, project: str
) -> tuple[str, None] | tuple[None, CommandOutcome]:
    env_uuid = _load_project_env(ctx, project).get("PROJECT_UUID", "").strip().lower()
    if not is_valid_uuid(env_uuid):
        return None, CommandOutcome(
            status="failed",
            error_code="project_uuid_unavailable",
            message="PROJECT_UUID ausente ou invalido no .env do projeto.",
        )
    return env_uuid, None


async def handle_backup_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    resolve_project_dir(ctx.config.projects_root, project, must_exist=True)
    project_uuid, failure = _resolve_backup_context(ctx, project)
    if failure is not None:
        return failure
    backup_id = str(args["backup_id"]).lower()
    backup_dir = resolve_backup_dir(ctx.config.backups_root, project_uuid, backup_id)
    if backup_dir.exists():
        return CommandOutcome(
            status="failed",
            error_code="backup_exists",
            message=f"Ponto de restauracao {backup_id} ja existe.",
        )
    ctx.state.report(
        progress=5,
        step="capture_backup",
        message="Capturando banco e storage do projeto...",
    )
    outcome, _ = await _run_lifecycle_script(
        ctx,
        "backup_project.sh",
        [project, backup_id],
        error_code="backup_failed",
    )
    if outcome.status == "done":
        size = await asyncio.to_thread(_dir_size_bytes, backup_dir)
        outcome.result = {**(outcome.result or {}), "size_bytes": size}
    return outcome


async def handle_restore_project(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    resolve_project_dir(ctx.config.projects_root, project, must_exist=True)
    project_uuid, failure = _resolve_backup_context(ctx, project)
    if failure is not None:
        return failure
    backup_id = str(args["backup_id"]).lower()
    safety_backup_id = str(args["safety_backup_id"]).lower()
    backup_dir = resolve_backup_dir(
        ctx.config.backups_root, project_uuid, backup_id, must_exist=True
    )
    if not (backup_dir / "manifest.json").is_file():
        return CommandOutcome(
            status="failed",
            error_code="backup_manifest_missing",
            message=f"Ponto {backup_id} sem manifest.json; backup invalido.",
        )
    safety_dir = resolve_backup_dir(
        ctx.config.backups_root, project_uuid, safety_backup_id
    )
    if safety_dir.exists():
        return CommandOutcome(
            status="failed",
            error_code="safety_backup_exists",
            message=f"Ponto de seguranca {safety_backup_id} ja existe.",
        )
    ctx.state.report(
        progress=5,
        step="restore_project",
        message=f"Restaurando {project} para o ponto {backup_id}...",
    )
    outcome, process = await _run_lifecycle_script(
        ctx,
        "restore_project.sh",
        [project, backup_id, safety_backup_id],
        error_code="restore_failed",
        markers=("SAFETY_BACKUP_COMPLETE", "ROLLBACK_COMPLETE"),
    )
    safety_completed = "SAFETY_BACKUP_COMPLETE" in process.markers_seen
    rolled_back = "ROLLBACK_COMPLETE" in process.markers_seen
    result = {
        "rolled_back": rolled_back,
        "safety_backup_completed": safety_completed,
    }
    if safety_completed:
        result["safety_backup_size_bytes"] = await asyncio.to_thread(
            _dir_size_bytes, safety_dir
        )
    outcome.result = {**(outcome.result or {}), **result}
    if outcome.status == "failed" and outcome.error_code == "restore_failed" and rolled_back:
        outcome.error_code = "restore_rolled_back"
    return outcome


async def handle_delete_restore_point(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    project_uuid, failure = _resolve_backup_context(ctx, project)
    if failure is not None:
        return failure
    backup_id = str(args["backup_id"]).lower()
    backup_dir = resolve_backup_dir(ctx.config.backups_root, project_uuid, backup_id)
    removed = await _remove_backup_tree(backup_dir)
    if backup_dir.exists():
        return CommandOutcome(
            status="failed",
            error_code="delete_backup_failed",
            message=f"Nao foi possivel remover o ponto {backup_id}.",
        )
    return CommandOutcome(status="done", result={"removed": removed})


async def handle_container_logs(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    service = str(args["service"])
    lines = int(args["lines"])
    container = f"supabase-{service}-{project}"

    code, stdout, _ = await _run_short(["docker", "inspect", container])
    if code != 0:
        return CommandOutcome(
            status="failed",
            error_code="container_not_found",
            message=f"Container {container} nao encontrado.",
        )
    container_state = "unknown"
    try:
        container_state = json.loads(stdout)[0].get("State", {}).get("Status", "unknown")
    except (ValueError, IndexError, AttributeError):
        pass

    code, logs, _ = await _run_short(
        ["docker", "logs", "--tail", str(lines), "--timestamps", container],
        timeout=45.0,
    )
    if code != 0:
        return CommandOutcome(status="failed", error_code="logs_failed", exit_code=code)
    return CommandOutcome(
        status="done",
        exit_code=0,
        result={
            "container": container,
            "status": container_state,
            "logs": sanitize_output(logs, tail_limit=CONTAINER_LOGS_LIMIT),
        },
    )


async def _tenant_api_command(
    ctx: CommandContext,
    project: str,
    *,
    container: str,
    method: str,
    path_template: str,
    token: str,
) -> CommandOutcome:
    if not token:
        return CommandOutcome(
            status="failed",
            error_code="token_missing",
            message="Sem credencial local para autenticar na API do tenant.",
        )
    status, body = await _tenant_curl(container, method, path_template, token)
    if status in TENANT_API_ACCEPTED_STATUSES:
        return CommandOutcome(status="done", result={"http_status": status})
    return CommandOutcome(
        status="failed",
        error_code="tenant_api_error",
        result={"http_status": status},
        message=sanitize_output(f"HTTP {status}: {body}", tail_limit=400),
    )


async def handle_terminate_supavisor_tenant(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    root_env = read_env_file(ctx.config.root / ".env")
    project_env = _load_project_env(ctx, project)
    issuer = _tenant_external_id(project_env, project)
    secret = root_env.get("JWT_SECRET", "").strip()
    token = _short_lived_jwt(secret, issuer) if secret else ""
    encoded = urllib.parse.quote(project, safe="")
    return await _tenant_api_command(
        ctx,
        project,
        container=SUPAVISOR_CONTAINER,
        method="GET",
        path_template=f"/api/tenants/{encoded}/terminate",
        token=token,
    )


async def handle_delete_supavisor_tenant(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    root_env = read_env_file(ctx.config.root / ".env")
    project_env = _load_project_env(ctx, project)
    issuer = _tenant_external_id(project_env, project)
    secret = root_env.get("JWT_SECRET", "").strip()
    token = _short_lived_jwt(secret, issuer) if secret else ""
    encoded = urllib.parse.quote(project, safe="")
    return await _tenant_api_command(
        ctx,
        project,
        container=SUPAVISOR_CONTAINER,
        method="DELETE",
        path_template=f"/api/tenants/{encoded}",
        token=token,
    )


async def handle_delete_realtime_tenant(ctx: CommandContext, project: str, args: dict[str, Any]) -> CommandOutcome:
    project_env = _load_project_env(ctx, project)
    tenant_external = _tenant_external_id(project_env, project)
    token = project_env.get("ANON_KEY_PROJETO", "").strip()
    if not token:
        jwt_secret = project_env.get("JWT_SECRET_PROJETO", "").strip()
        token = _short_lived_jwt(jwt_secret, tenant_external) if jwt_secret else ""
    encoded = urllib.parse.quote(tenant_external, safe="")
    return await _tenant_api_command(
        ctx,
        project,
        container=REALTIME_CONTAINER,
        method="DELETE",
        path_template=f"/api/tenants/{encoded}",
        token=token,
    )


CommandHandler = Callable[[CommandContext, str, dict[str, Any]], Awaitable[CommandOutcome]]

COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "start_project": handle_start_project,
    "stop_project": handle_stop_project,
    "restart_project": handle_restart_project,
    "recreate_services": handle_recreate_services,
    "create_project": handle_create_project,
    "duplicate_project": handle_duplicate_project,
    "delete_project_containers": handle_delete_project_containers,
    "delete_project_files": handle_delete_project_files,
    "rotate_keys": handle_rotate_keys,
    "rename_project": handle_rename_project,
    "backup_project": handle_backup_project,
    "restore_project": handle_restore_project,
    "delete_restore_point": handle_delete_restore_point,
    "container_logs": handle_container_logs,
    "terminate_supavisor_tenant": handle_terminate_supavisor_tenant,
    "delete_supavisor_tenant": handle_delete_supavisor_tenant,
    "delete_realtime_tenant": handle_delete_realtime_tenant,
}
