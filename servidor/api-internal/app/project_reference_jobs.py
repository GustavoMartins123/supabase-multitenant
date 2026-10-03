"""Durable completion of public-reference rotations executed by the host-agent."""

import uuid

from app.control_plane_service import audit_studio_action, create_studio_notification
from app.database import get_pool
from app.host_agent import command_result, run_command_for_job
from app.jobs import set_job_status
from app.project_public_ref import validate_public_ref


async def rename_project_background(
    job_id: str,
    project_id: uuid.UUID,
    history_id: int,
    old_ref: str,
    new_ref: str,
    actor_user_id: uuid.UUID,
) -> None:
    from app.project_backgrounds import _job_progress_mirror, _update_rename_history

    pool = await get_pool()
    try:
        validate_public_ref(old_ref)
        validate_public_ref(new_ref)
        async with pool.acquire() as conn:
            history = await conn.fetchrow(
                "SELECT * FROM project_reference_history WHERE id=$1 AND job_id=$2",
                history_id,
                uuid.UUID(str(job_id)),
            )
            project = await conn.fetchrow(
                "SELECT name,tenant_uuid,public_ref FROM projects WHERE id=$1", project_id
            )
            if (
                not history
                or not project
                or history["project_id"] != project_id
                or history["old_ref"] != old_ref
                or history["new_ref"] != new_ref
                or history["actor_user_id"] != actor_user_id
            ):
                raise RuntimeError("Durable reference rotation identity changed")
            if history["status"] in {"succeeded", "failed", "rolled_back"}:
                await set_job_status(
                    job_id,
                    "done" if history["status"] == "succeeded" else "failed",
                    current_step="completed",
                    message="Rotacao ja finalizada.",
                )
                return
            await _update_rename_history(conn, history_id, "running")
        await set_job_status(
            job_id,
            "running",
            message="Atualizando URL publica sem mover infraestrutura.",
            progress=5,
            current_step="rotate_public_reference",
            total_steps=4,
        )
        record = await run_command_for_job(
            pool,
            job_id=job_id,
            command="rename_project",
            project=project["name"],
            project_uuid=project_id,
            requested_by=actor_user_id,
            args={
                "old_ref": old_ref,
                "new_ref": new_ref,
                "tenant_uuid": str(project["tenant_uuid"]),
            },
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        result = command_result(record)
        async with pool.acquire() as conn:
            async with conn.transaction():
                history = await conn.fetchrow(
                    "SELECT status FROM project_reference_history WHERE id=$1 FOR UPDATE",
                    history_id,
                )
                canonical = await conn.fetchrow(
                    "SELECT name,tenant_uuid,public_ref FROM projects WHERE id=$1", project_id
                )
                succeeded = record["status"] == "done"
                if succeeded and (
                    not canonical
                    or canonical["name"] != project["name"]
                    or canonical["tenant_uuid"] != project["tenant_uuid"]
                    or canonical["public_ref"] != new_ref
                    or result.get("old_ref") != old_ref
                    or result.get("new_ref") != new_ref
                ):
                    raise RuntimeError("Host completion does not match the canonical reference")
                rolled_back = (
                    not succeeded
                    and result.get("rolled_back") is True
                    and canonical
                    and canonical["name"] == project["name"]
                    and canonical["tenant_uuid"] == project["tenant_uuid"]
                    and canonical["public_ref"] == old_ref
                    and result.get("old_ref") == old_ref
                    and result.get("new_ref") == new_ref
                )
                status = "succeeded" if succeeded else "rolled_back" if rolled_back else "failed"
                message = (
                    "URL publica atualizada; infraestrutura e dados preservados."
                    if succeeded
                    else "Rotacao falhou e foi revertida."
                    if rolled_back
                    else "Rotacao falhou; recuperacao explicita necessaria."
                )
                if history["status"] not in {"succeeded", "failed", "rolled_back"}:
                    await _update_rename_history(
                        conn, history_id, status, error=None if succeeded else record["error_code"]
                    )
                    await audit_studio_action(
                        conn,
                        project_id=project_id,
                        actor_user_id=actor_user_id,
                        action="project_rename_" + status,
                        target_type="project",
                        target_id=old_ref,
                        old_value={"ref": old_ref, "path": "/" + old_ref},
                        new_value={
                            "ref": new_ref,
                            "path": "/" + new_ref,
                            "error_code": record["error_code"],
                        },
                    )
                    if succeeded:
                        targets = await conn.fetch(
                            "SELECT user_id FROM project_members WHERE project_id=$1 AND user_id<>$2",
                            project_id,
                            actor_user_id,
                        )
                        for target in targets:
                            await create_studio_notification(
                                conn,
                                project_id=project_id,
                                target_user_id=target["user_id"],
                                actor_user_id=actor_user_id,
                                kind="project_renamed",
                                target_type="project",
                                target_id=str(project_id),
                                payload={
                                    "old_ref": old_ref,
                                    "new_ref": new_ref,
                                    "old_path": "/" + old_ref,
                                    "new_path": "/" + new_ref,
                                },
                            )
                await conn.execute(
                    "UPDATE jobs SET status=$1, message=$2, progress=$3, current_step=$4, error_code=$5, finished_at=now(), updated_at=now() WHERE job_id=$6",
                    "done" if succeeded else "failed",
                    message,
                    100 if succeeded else record["progress"] or 0,
                    "completed"
                    if succeeded
                    else "rollback_completed"
                    if rolled_back
                    else "rollback_unconfirmed",
                    None if succeeded else record["error_code"],
                    uuid.UUID(str(job_id)),
                )
    except Exception as exc:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _update_rename_history(
                    conn, history_id, "failed", error="rotation_completion_unconfirmed"
                )
                await conn.execute(
                    "UPDATE jobs SET status='failed', message=$1, error_code='rotation_completion_unconfirmed', finished_at=now(), updated_at=now() WHERE job_id=$2",
                    "Falha ao confirmar a rotacao da referencia publica.",
                    uuid.UUID(str(job_id)),
                )
        print(f"[reference-rotation] {project_id}: {type(exc).__name__}")
