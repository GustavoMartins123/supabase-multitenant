"""Contrato de identidade do control plane, independente do transporte."""

from typing import Annotated

from pydantic import BaseModel, Field
from app.host_agent_protocol import ProjectNameValidator

CanonicalUuid = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", min_length=36, max_length=36)]
PublicRef = Annotated[str, Field(pattern=r"^[a-z]{20}$", min_length=20, max_length=20)]
ProjectName = Annotated[str, Field(pattern=ProjectNameValidator.NAME_RE.pattern, min_length=3, max_length=40)]
DisplayName = Annotated[str, Field(min_length=1, max_length=80, pattern=r"\S")]


class ProjectIdentity(BaseModel):
    project_uuid: CanonicalUuid
    tenant_uuid: CanonicalUuid | None
    name: ProjectName
    public_ref: PublicRef
    display_name: DisplayName


class JobIdentity(BaseModel):
    job_id: CanonicalUuid
    project: ProjectName
    public_ref: PublicRef | None
    project_uuid: CanonicalUuid | None
    tenant_uuid: CanonicalUuid | None
    created_by: CanonicalUuid | None
