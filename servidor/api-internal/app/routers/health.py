"""Endpoints públicos usados apenas por probes do orquestrador."""

from fastapi import APIRouter


router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, bool]:
    return {"ok": True}
