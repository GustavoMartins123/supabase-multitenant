"""Identidade canonica do projeto e vinculo com o tenant externo.

``projects.id`` identifica o projeto no control plane. ``projects.tenant_uuid``
persiste o identificador usado pelo Realtime, JWT issuer e backups. Projetos
novos usam o mesmo UUID nos dois campos; a coluna separada preserva o vinculo
de instalacoes legadas sem reescrever tenants existentes.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import dotenv_values


class ProjectIdentityError(RuntimeError):
    pass


class ProjectIdentityConflict(ProjectIdentityError):
    pass


@dataclass(frozen=True)
class ProjectIdentityReconciliation:
    migrated: int
    already_persisted: int
    unresolved: tuple[str, ...]


async def get_job_project_identity(
    pool: asyncpg.Pool,
    job_id: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolve a identidade duravel do job sem gerar UUID no worker."""
    row = await pool.fetchrow(
        """
        SELECT
            j.project_uuid,
            j.payload,
            p.tenant_uuid,
            (
                SELECT hc.args->>'tenant_uuid'
                FROM host_agent_commands hc
                WHERE hc.job_id = j.job_id
                  AND hc.args ? 'tenant_uuid'
                ORDER BY hc.created_at DESC
                LIMIT 1
            ) AS command_tenant_uuid
        FROM jobs j
        LEFT JOIN projects p ON p.id = j.project_uuid
        WHERE j.job_id = $1
        """,
        uuid.UUID(str(job_id)),
    )
    if row is None or row["project_uuid"] is None:
        raise ProjectIdentityError(f"Job {job_id} sem projects.id canonico")

    project_uuid = uuid.UUID(str(row["project_uuid"]))
    payload = row["payload"] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    candidates = {
        candidate
        for candidate in (
            parse_tenant_uuid(row["tenant_uuid"]),
            parse_tenant_uuid(payload.get("tenant_uuid")),
            parse_tenant_uuid(row["command_tenant_uuid"]),
        )
        if candidate is not None
    }
    if not candidates:
        raise ProjectIdentityError(
            f"Projeto {project_uuid} sem tenant_uuid persistido"
        )
    if len(candidates) > 1:
        raise ProjectIdentityError(
            f"Projeto {project_uuid} possui tenant_uuid divergente"
        )

    tenant_uuid = candidates.pop()
    if row["tenant_uuid"] is None:
        await pool.execute(
            """
            UPDATE projects SET tenant_uuid = $2
            WHERE id = $1 AND tenant_uuid IS NULL
            """,
            project_uuid,
            tenant_uuid,
        )
    return project_uuid, tenant_uuid


def parse_tenant_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (AttributeError, TypeError, ValueError):
        return None


def read_project_tenant_uuid(projects_root: Path, project_name: str) -> uuid.UUID | None:
    """Le PROJECT_UUID sem permitir que nome/symlink escape de projects_root."""
    root = projects_root.resolve()
    project_dir = (root / project_name).resolve()
    if project_dir.parent != root:
        return None
    env_path = project_dir / ".env"
    if not env_path.is_file():
        return None
    values = dotenv_values(env_path)
    return parse_tenant_uuid(values.get("PROJECT_UUID"))


def _project_artifacts_exist(projects_root: Path, project_name: str) -> bool:
    """Trata caminho inseguro ou diretorio existente como estado ja iniciado."""
    root = projects_root.resolve()
    project_dir = (root / project_name).resolve()
    if project_dir.parent != root:
        return True
    return project_dir.exists()


async def reconcile_project_tenant_uuids(
    pool: asyncpg.Pool,
    projects_root: Path,
) -> ProjectIdentityReconciliation:
    """Backfill seguro: .env -> comando duravel -> id para linha pendente.

    Projetos provisionados sem qualquer evidencia ficam nulos para revisao;
    assumir ``projects.id`` nesses casos poderia apontar para o tenant errado.
    Qualquer divergencia observavel falha o startup antes de operacoes fisicas.
    """
    rows = await pool.fetch(
        """
        SELECT
            p.id,
            p.name,
            p.tenant_uuid,
            p.anon_key IS NOT NULL AS is_provisioned,
            (
                SELECT hc.args->>'tenant_uuid'
                FROM host_agent_commands hc
                WHERE hc.project_uuid = p.id
                  AND hc.command IN ('create_project', 'duplicate_project')
                  AND hc.args ? 'tenant_uuid'
                ORDER BY (hc.status = 'done') DESC, hc.created_at DESC
                LIMIT 1
            ) AS command_tenant_uuid
        FROM projects p
        ORDER BY p.name
        """
    )

    updates: list[tuple[uuid.UUID, uuid.UUID]] = []
    unresolved: list[str] = []
    conflicts: list[str] = []
    resolved_owners: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    already_persisted = 0

    for row in rows:
        project_id = uuid.UUID(str(row["id"]))
        project_name = str(row["name"])
        persisted = parse_tenant_uuid(row["tenant_uuid"])
        from_env = read_project_tenant_uuid(projects_root, project_name)
        from_command = parse_tenant_uuid(row["command_tenant_uuid"])

        evidence = {
            source: value
            for source, value in ((".env", from_env), ("comando", from_command))
            if value is not None
        }
        if persisted is not None:
            already_persisted += 1
            mismatches = [
                f"{source}={value}"
                for source, value in evidence.items()
                if value != persisted
            ]
            if mismatches:
                conflicts.append(
                    f"{project_name}: persistido={persisted}; " + ", ".join(mismatches)
                )
            selected = persisted
        else:
            candidates = set(evidence.values())
            if len(candidates) > 1:
                conflicts.append(
                    f"{project_name}: .env={from_env}; comando={from_command}"
                )
                continue
            if candidates:
                selected = candidates.pop()
            elif not bool(row["is_provisioned"]) and not _project_artifacts_exist(
                projects_root, project_name
            ):
                # Linha pendente sem chaves nem artefatos: ainda nao existe
                # identidade externa estabelecida, portanto pode adotar o UUID
                # canonico sem risco de apontar para outro tenant.
                selected = project_id
            else:
                unresolved.append(project_name)
                continue
            updates.append((project_id, selected))

        previous = resolved_owners.get(selected)
        if previous is not None and previous[0] != project_id:
            conflicts.append(
                f"tenant {selected} pertence a {previous[1]} e {project_name}"
            )
        else:
            resolved_owners[selected] = (project_id, project_name)

    if conflicts:
        raise ProjectIdentityConflict(
            "Conflito de identidade de tenant: " + "; ".join(conflicts)
        )

    if updates:
        await pool.executemany(
            """
            UPDATE projects
            SET tenant_uuid = $2
            WHERE id = $1 AND tenant_uuid IS NULL
            """,
            updates,
        )

    return ProjectIdentityReconciliation(
        migrated=len(updates),
        already_persisted=already_persisted,
        unresolved=tuple(unresolved),
    )
